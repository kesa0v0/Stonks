from fastapi import Request, status
from fastapi.responses import JSONResponse
from backend.core import exceptions

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
        
    return JSONResponse(
        status_code=status_code,
        content={"detail": exc.message},
    )
