from locust import HttpUser, task, between
import random

class StonksUser(HttpUser):
    # 유저가 행동하는 대기 시간 (1초 ~ 3초 사이 랜덤)
    wait_time = between(1, 3)
    
    # 테스트용 계정 정보 (create_test_user.py에 정의된 값)
    username = "test@kesa.uk"
    password = "test1234"
    token = None
    headers = {} # 초기화
    ticker_ids = []

    def on_start(self):
        """테스트 시작 시 1회 실행: 로그인 및 토큰 획득"""
        try:
            response = self.client.post("/api/v1/auth/login/access-token", data={
                "username": self.username,
                "password": self.password
            })
            
            if response.status_code == 200:
                self.token = response.json()["access_token"]
                self.headers = {"Authorization": f"Bearer {self.token}"}
                print(f"✅ Login Successful: {self.username}")
                
                # 티커 목록 미리 확보 (주문 넣을 때 쓰기 위해)
                ticker_res = self.client.get("/api/v1/market/tickers", headers=self.headers)
                if ticker_res.status_code == 200:
                    self.ticker_ids = [t['id'] for t in ticker_res.json()]
            else:
                print(f"❌ Login Failed: {response.status_code} - {response.text}")
                self.stop()
        except Exception as e:
            print(f"❌ Login Exception: {e}")
            self.stop()

    @task(3)
    def view_market_tickers(self):
        """가장 자주 하는 행동: 전체 시세 조회"""
        if not self.token: return # 토큰 없으면 스킵
        self.client.get("/api/v1/market/tickers", headers=self.headers)

    @task(1)
    def place_order(self):
        """주문 넣기 (부하가 큼)"""
        if not self.token or not self.ticker_ids: return # 토큰 없거나 종목 정보 없으면 스킵

        ticker_id = random.choice(self.ticker_ids)
        
        # 매수/매도 랜덤
        side = random.choice(["BUY", "SELL"])
        # 가격은 대충 랜덤
        price = random.randint(100, 1000)
        
        payload = {
            "ticker_id": ticker_id,
            "side": side,
            "type": "LIMIT",
            "quantity": 1,
            "target_price": price
        }
        
        # 실패해도 테스트가 멈추지 않도록 catch_response 사용
        with self.client.post("/api/v1/orders", json=payload, headers=self.headers, catch_response=True) as response:
            if response.status_code == 200:
                response.success()
            elif response.status_code == 400:
                # 잔액 부족 등 로직상 에러는 시스템 에러가 아니므로 성공 처리하거나 무시
                # response.failure(f"Logic Error: {response.text}") 
                pass # 그냥 무시 (부하 테스트니까)
            else:
                response.failure(f"System Error: {response.status_code}")

    @task(2)
    def view_portfolio(self):
        """내 포트폴리오 확인"""
        if not self.token: return # 토큰 없으면 스킵
        self.client.get("/api/v1/me/portfolio", headers=self.headers)