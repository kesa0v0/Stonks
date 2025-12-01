import streamlit as st
import requests
import pandas as pd
import os

# 백엔드 API 주소 (로컬 개발 환경 가정)
API_URL = os.getenv("API_URL", "http://localhost:8000/api/v1")

st.set_page_config(page_title="Stonks Admin", layout="wide")

if "token" not in st.session_state:
    st.session_state.token = None

def login():
    st.title("🔒 Admin Login")
    with st.form("login_form"):
        username = st.text_input("Email")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Login")
        
        if submitted:
            try:
                # 로그인 시도
                res = requests.post(f"{API_URL}/auth/login/access-token", data={
                    "username": username,
                    "password": password
                })
                
                if res.status_code == 200:
                    token = res.json()["access_token"]
                    st.session_state.token = token
                    st.success("Login Successful!")
                    st.rerun()
                else:
                    st.error(f"Login Failed: {res.text}")
            except Exception as e:
                st.error(f"Connection Error: {e}")

def main_app():
    st.sidebar.title("Stonks Admin")
    if st.sidebar.button("Logout"):
        st.session_state.token = None
        st.rerun()
    
    headers = {"Authorization": f"Bearer {st.session_state.token}"}
    
    tab1, tab2, tab3, tab4 = st.tabs(["👥 Users", "📈 Tickers", "📢 Notice", "⚙️ Settings"])
    
    # --- Tab 1: Users ---
    with tab1:
        st.header("User Management")
        
        col1, col2 = st.columns([1, 3])
        with col1:
            if st.button("Refresh Users"):
                try:
                    res = requests.get(f"{API_URL}/admin/users", headers=headers)
                    if res.status_code == 200:
                        users = res.json()
                        st.session_state.users_df = pd.DataFrame(users)
                    else:
                        st.error(f"Failed to load users: {res.text}")
                except Exception as e:
                    st.error(f"Error: {e}")
        
        if "users_df" in st.session_state:
            st.dataframe(st.session_state.users_df, use_container_width=True)
            
            st.subheader("Actions")
            target_user_id = st.text_input("Target User ID (UUID)")
            
            col_act1, col_act2 = st.columns(2)
            
            with col_act1:
                with st.expander("Force Bankruptcy"):
                    if st.button("Execute Bankruptcy"):
                        if target_user_id:
                            r = requests.post(f"{API_URL}/admin/users/{target_user_id}/bankruptcy", headers=headers)
                            if r.status_code == 200:
                                st.success(f"User {target_user_id} bankrupted successfully")
                            else:
                                st.error(f"Failed: {r.text}")
                                
            with col_act2:
                with st.expander("Ban / Unban User"):
                    action = st.radio("Action", ["Ban (Deactivate)", "Unban (Activate)"])
                    if st.button("Update Status"):
                        if target_user_id:
                            is_active = True if "Unban" in action else False
                            r = requests.put(f"{API_URL}/admin/users/{target_user_id}/status", json={"is_active": is_active}, headers=headers)
                            if r.status_code == 200:
                                st.success(f"User status updated: {action}")
                            else:
                                st.error(f"Failed: {r.text}")

    # --- Tab 2: Tickers ---
    with tab2:
        st.header("Ticker Management")
        
        col1, col2 = st.columns([1, 3])
        with col1:
            if st.button("Refresh Tickers"):
                try:
                    # 관리자 전용 API가 없으므로 일반 마켓 API 사용 (활성 종목만 나올 수 있음)
                    # 만약 비활성 종목도 보고 싶다면 백엔드에 admin 전용 list API 필요
                    # 일단은 /market/tickers 사용
                    res = requests.get(f"{API_URL}/market/tickers", headers=headers)
                    if res.status_code == 200:
                        tickers = res.json()
                        st.session_state.tickers_df = pd.DataFrame(tickers)
                    else:
                        st.error(f"Failed to load tickers: {res.text}")
                except Exception as e:
                    st.error(f"Error: {e}")

        if "tickers_df" in st.session_state and not st.session_state.tickers_df.empty:
            df = st.session_state.tickers_df
            st.dataframe(df, use_container_width=True)
            
            st.subheader("Edit / Delete Ticker")
            selected_ticker_id = st.selectbox("Select Ticker to Edit", df['id'].tolist())
            
            if selected_ticker_id:
                ticker_info = df[df['id'] == selected_ticker_id].iloc[0]
                
                with st.expander(f"Edit {selected_ticker_id}", expanded=True):
                    with st.form("edit_ticker"):
                        new_name = st.text_input("Name", value=ticker_info['name'])
                        new_is_active = st.checkbox("Is Active", value=ticker_info.get('is_active', True))
                        
                        c1, c2 = st.columns(2)
                        with c1:
                            update_submitted = st.form_submit_button("Update Ticker")
                        with c2:
                            delete_submitted = st.form_submit_button("DELETE Ticker", type="primary")
                            
                        if update_submitted:
                            payload = {"name": new_name, "is_active": new_is_active}
                            r = requests.put(f"{API_URL}/admin/tickers/{selected_ticker_id}", json=payload, headers=headers)
                            if r.status_code == 200:
                                st.success("Ticker Updated")
                            else:
                                st.error(r.text)
                                
                        if delete_submitted:
                            r = requests.delete(f"{API_URL}/admin/tickers/{selected_ticker_id}", headers=headers)
                            if r.status_code == 200:
                                st.warning("Ticker Deleted")
                            else:
                                st.error(r.text)

        # Add New Ticker
        st.divider()
        st.subheader("Add New Ticker")
        with st.expander("Create Form"):
            with st.form("new_ticker"):
                col_a, col_b = st.columns(2)
                with col_a:
                    tid = st.text_input("ID (e.g. KRX-STOCK-SANDBOX)")
                    symbol = st.text_input("Symbol (e.g. SAND/KRW)")
                with col_b:
                    name = st.text_input("Name")
                    mtype = st.selectbox("Type", ["KRX", "US", "CRYPTO"])
                    currency = st.selectbox("Currency", ["KRW", "USD"])
                
                submitted = st.form_submit_button("Create Ticker")
                if submitted:
                    payload = {
                        "id": tid, "symbol": symbol, "name": name,
                        "market_type": mtype, "currency": currency,
                        "is_active": True
                    }
                    r = requests.post(f"{API_URL}/admin/tickers", json=payload, headers=headers)
                    if r.status_code == 200:
                        st.success("Ticker Created")
                    else:
                        st.error(r.text)

    # --- Tab 3: Notice ---
    with tab3:
        st.header("System Notice")
        notice_msg = st.text_area("Broadcast Message to All Users")
        if st.button("Post Notice"):
            r = requests.post(f"{API_URL}/admin/notice", json={"message": notice_msg}, headers=headers)
            if r.status_code == 200:
                st.success("Notice Posted!")
            else:
                st.error(r.text)

    # --- Tab 4: Settings (Fee) ---
    with tab4:
        st.header("Trading Fee")
        if st.button("Load Current Fee"):
             r = requests.get(f"{API_URL}/admin/fee", headers=headers)
             if r.status_code == 200:
                 st.info(f"Current Fee Rate: {r.json()['fee_rate']}")
        
        new_fee = st.number_input("New Fee Rate (e.g. 0.001 for 0.1%)", format="%.4f", step=0.0001)
        if st.button("Update Fee"):
            r = requests.put(f"{API_URL}/admin/fee", json={"fee_rate": new_fee}, headers=headers)
            if r.status_code == 200:
                st.success("Fee Updated Successfully")
            else:
                st.error(r.text)

if st.session_state.token:
    main_app()
else:
    login()
