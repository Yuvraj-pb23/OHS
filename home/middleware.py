import time
from django.contrib.auth import logout
from django.shortcuts import redirect
from django.core.cache import cache
import uuid

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
