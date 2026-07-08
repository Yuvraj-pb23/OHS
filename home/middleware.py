import time
from django.contrib.auth import logout
from django.http import HttpResponseForbidden
from django.shortcuts import redirect
from django.core.cache import cache
import uuid

# FIX #6: Protect sensitive media paths from unauthenticated access.
# Payment screenshots, certificates, and uploaded training resources must
# only be accessible to authenticated users.
PROTECTED_MEDIA_PREFIXES = (
    "posh_payments/",
    "pocso_payments/",
    "Certificate/",
    "training_videos/",
    "training_materials/",
)

class MediaAuthMiddleware:
    """
    FIX #6: Intercepts /media/ requests and enforces authentication for
    sensitive directories (payment proofs, certificates, training content).
    Static posters and logos remain publicly accessible.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith("/media/"):
            relative = request.path[len("/media/"):]
            if any(relative.startswith(prefix) for prefix in PROTECTED_MEDIA_PREFIXES):
                if not request.user.is_authenticated:
                    return redirect(f"/login/?next={request.path}")
        return self.get_response(request)


class TabCloseSessionMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Skip check for the tab-close endpoint itself
        if request.path == '/session/tab-close/':
            return self.get_response(request)

        # Exclude static assets and media files from session checks
        path = request.path.lower()
        if any(path.endswith(ext) for ext in ['.css', '.js', '.png', '.jpg', '.jpeg', '.gif', '.svg', '.ico', '.woff', '.woff2', '.ttf', '.map']):
            return self.get_response(request)

        if request.user.is_authenticated:
            session_key = request.session.session_key
            if session_key:
                # Check if we have an unload pending timestamp in the cache
                unload_pending_at = cache.get(f"unload_pending_at_{session_key}")
                if unload_pending_at is not None:
                    # If a new request comes in within 15 seconds of tab close, keep session active
                    if time.time() - unload_pending_at < 15.0:
                        cache.delete(f"unload_pending_at_{session_key}")
                    else:
                        # Genuine tab close: log out
                        is_accounts = (getattr(request.user, 'account_type', None) == 'ACCOUNTS') or request.path.startswith('/accounts-portal/')
                        logout(request)
                        if is_accounts:
                            return redirect('accounts_login')
                        return redirect('login')

                # On standard page loads (GET document requests), assign a unique Page Load ID
                is_ajax = (request.headers.get('x-requested-with') == 'XMLHttpRequest') or (request.META.get('HTTP_X_REQUESTED_WITH') == 'XMLHttpRequest')
                if request.method == 'GET' and not is_ajax:
                    new_id = uuid.uuid4().hex
                    request.page_load_id = new_id
                    
                    # Add this tab ID to active tabs tracking in the cache
                    active_tabs = cache.get(f"active_tabs_{session_key}", [])
                    if new_id not in active_tabs:
                        active_tabs.append(new_id)
                    cache.set(f"active_tabs_{session_key}", active_tabs, timeout=86400)
                    
                    # Explicitly clear any pending unloads in the cache
                    cache.delete(f"unload_pending_at_{session_key}")

        response = self.get_response(request)
        return response


class SecurityHeadersMiddleware:
    """
    FIX #9: Adds Content-Security-Policy and other security headers to every HTTP response.
    These headers harden the browser against XSS, clickjacking, MIME sniffing,
    and information leakage attacks.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        # Content-Security-Policy
        # - default-src 'self': Only load resources from same origin by default
        # - script-src / style-src: allow inline (existing templates use inline JS/CSS)
        #   and trusted CDNs (Google Fonts, etc.)
        # - img-src: allow data URIs (charts, captcha) and S3 (training video thumbnail)
        # - media-src: allow S3 for training videos
        # - frame-ancestors 'none': no embedding in iframes (same as X-Frame-Options DENY)
        # FIX #11: Removed 'unsafe-eval' — eval(), setTimeout(string) etc. are now blocked.
        # 'unsafe-inline' is retained until inline scripts are migrated to external files.
        csp = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' "
            "https://cdnjs.cloudflare.com https://cdn.jsdelivr.net "
            "https://fonts.googleapis.com https://cdn.tailwindcss.com; "
            "style-src 'self' 'unsafe-inline' "
            "https://fonts.googleapis.com https://cdnjs.cloudflare.com "
            "https://cdn.jsdelivr.net https://cdn.tailwindcss.com; "
            "font-src 'self' https://fonts.gstatic.com https://cdnjs.cloudflare.com "
            "https://cdn.jsdelivr.net data:; "
            "img-src 'self' data: blob: https: http:; "
            "media-src 'self' https://website-data-593333832687-ap-south-1-an.s3.ap-south-1.amazonaws.com; "
            "connect-src 'self'; "
            "frame-ancestors 'none'; "
            "object-src 'none';"
        )
        response["Content-Security-Policy"] = csp

        # Prevent MIME-type sniffing
        response["X-Content-Type-Options"] = "nosniff"

        # Referrer-Policy: don't leak URL to third parties
        response["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # Permissions-Policy: disable unused powerful browser features
        response["Permissions-Policy"] = (
            "geolocation=(), microphone=(), camera=(), payment=()"
        )

        return response
