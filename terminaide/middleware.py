# terminaide/middleware.py
from starlette.middleware.base import BaseHTTPMiddleware
import logging

logger = logging.getLogger("terminaide")

class ProxyHeaderMiddleware(BaseHTTPMiddleware):
    """
    Middleware that detects and respects common proxy headers for HTTPS, enabling
    terminaide to work correctly behind load balancers and proxies.
    """
    
    async def dispatch(self, request, call_next):
        # Check X-Forwarded-Proto (most common)
        forwarded_proto = request.headers.get("x-forwarded-proto")
        if forwarded_proto == "https":
            original_scheme = request.scope.get("scheme", "unknown")
            request.scope["scheme"] = "https"
            
            # Log this detection once per deployment to help with debugging
            logger.debug(
                f"HTTPS detected via X-Forwarded-Proto header "
                f"(original scheme: {original_scheme})"
            )
        
        # Check Forwarded header (RFC 7239)
        forwarded = request.headers.get("forwarded")
        if forwarded and "proto=https" in forwarded.lower():
            request.scope["scheme"] = "https"
        
        # AWS Elastic Load Balancer sometimes uses this
        elb_proto = request.headers.get("x-forwarded-protocol")
        if elb_proto == "https":
            request.scope["scheme"] = "https"
        
        return await call_next(request)