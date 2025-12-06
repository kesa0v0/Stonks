from fastapi import Request, status
from fastapi.responses import JSONResponse
from backend.core import exceptions
from backend.core.notify import send_ntfy_notification
import logging

logger = logging.getLogger(__name__)

async def stonks_exception_handler(request: Request, exc: exceptions.StonksError):
    status_code = status.HTTP_400_BAD_REQUEST
    
    if isinstance(exc, exceptions.EntityNotFoundError):
        status_code = status.HTTP_404_NOT_FOUND
    
    elif isinstance(exc, exceptions.EntityAlreadyExistsError):
        status_code = status.HTTP_400_BAD_REQUEST
        
    elif isinstance(exc, exceptions.AuthError):
        if isinstance(exc, exceptions.InvalidCredentialsError):
            status_code = status.HTTP_401_UNAUTHORIZED
        elif isinstance(exc, exceptions.PermissionDeniedError):
            status_code = status.HTTP_403_FORBIDDEN
        else:
            status_code = status.HTTP_400_BAD_REQUEST
            
    elif isinstance(exc, exceptions.OrderSystemError):
        status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        # 시스템 에러는 관리자 알림 전송
        await send_ntfy_notification(
            message=f"Order System Error: {exc.message}", 
            title="🚨 Critical Order Error", 
            priority="high"
        )
        
    return JSONResponse(
        status_code=status_code,
        content={"detail": exc.message},
    )

async def general_exception_handler(request: Request, exc: Exception):
    # 예상치 못한 모든 에러 처리
    error_msg = f"Unhandled Exception: {str(exc)}\nPath: {request.url.path}"
    logger.error(f"❌ {error_msg}", exc_info=True)
    
    await send_ntfy_notification(
        message=error_msg, 
        title="🔥 500 Internal Server Error", 
        priority="max"
    )
    
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal Server Error. Admin has been notified."},
    )
