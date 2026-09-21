import hashlib

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import F, Sum
from django.http import Http404, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from .models import MarketingCampaign, MarketingPayout, MarketingShare, MarketingView


def _fingerprint(request, campaign):
    """A stable per-visitor identifier — IP + user agent + campaign. Not
    perfect (shared NATs collapse into one) but good enough to stop
    casual refresh spam."""
    raw = '|'.join([
        request.META.get('HTTP_X_FORWARDED_FOR', request.META.get('REMOTE_ADDR', '')),
        request.META.get('HTTP_USER_AGENT', ''),
        str(campaign.id),
    ])
    return hashlib.sha256(raw.encode()).hexdigest()


@require_GET
def campaign_list(request):
    """Shows the live campaign (or the latest one) and the user's share
    + earnings for it."""
    campaign = (
        MarketingCampaign.objects
        .filter(is_active=True, starts_at__lte=timezone.now())
        .order_by('-created_at')
        .first()
    )
    if campaign is None:
        return render(request, 'marketing/list.html', {'campaign': None})

    share = None
    if request.user.is_authenticated:
        share = MarketingShare.objects.filter(user=request.user, campaign=campaign).first()

    return render(request, 'marketing/list.html', {
        'campaign': campaign,
        'share': share,
    })


@login_required
@require_POST
def create_share(request, campaign_id):
    campaign = get_object_or_404(MarketingCampaign, id=campaign_id)
    if not campaign.is_live:
        messages.error(request, 'This campaign is no longer active.')
        return redirect('marketing:list')

    share, created = MarketingShare.objects.get_or_create(
        user=request.user, campaign=campaign,
    )
    if created:
        messages.success(request, 'Your share link is ready — copy it and post it to WhatsApp.')
    else:
        messages.info(request, 'Here is your existing share link for this campaign.')
    return redirect('marketing:list')


@require_GET
def redirect_view(request, code):
    """The public landing URL of a share link. Records a unique view,
    credits the sharer, then 302s to the campaign's destination."""
    share = get_object_or_404(MarketingShare, code=code)
    campaign = share.campaign

    if campaign.is_live:
        fp = _fingerprint(request, campaign)
        try:
            with transaction.atomic():
                _, created = MarketingView.objects.get_or_create(
                    share=share, fingerprint=fp,
                    defaults={
                        'user_agent': request.META.get('HTTP_USER_AGENT', '')[:300],
                        'referer': request.META.get('HTTP_REFERER', '')[:300],
                    },
                )
                if created:
                    MarketingShare.objects.filter(pk=share.pk).update(
                        views=F('views') + 1,
                        earnings=F('earnings') + campaign.payout_per_view,
                        last_view_at=timezone.now(),
                    )
                    # Mirror the totals into the payout row.
                    payout, _ = MarketingPayout.objects.get_or_create(
                        user=share.user, campaign=campaign,
                    )
                    MarketingPayout.objects.filter(pk=payout.pk).update(
                        views=F('views') + 1,
                        amount=F('amount') + campaign.payout_per_view,
                    )
        except Exception:
            # Never block the redirect on analytics failure.
            pass

    return HttpResponseRedirect(campaign.landing_url)


@login_required
@require_GET
def my_earnings(request):
    shares = (
        MarketingShare.objects
        .filter(user=request.user)
        .select_related('campaign')
        .order_by('-created_at')
    )
    totals = shares.aggregate(
        views=Sum('views'),
        earnings=Sum('earnings'),
    )
    return render(request, 'marketing/earnings.html', {
        'shares': shares,
        'total_views': totals['views'] or 0,
        'total_earnings': totals['earnings'] or 0,
    })