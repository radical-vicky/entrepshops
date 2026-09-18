class ReferralCaptureMiddleware:
    """If a link like /?ref=AB12CD3 is visited, remember the code in the
    session so it's still there by the time the person finishes signing up
    (whether that's a form submit or a Google OAuth round-trip)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        code = request.GET.get('ref')
        if code:
            request.session['referral_code'] = code.strip().upper()
        return self.get_response(request)
