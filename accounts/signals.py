from allauth.account.signals import user_signed_up
from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Profile

User = get_user_model()


@receiver(post_save, sender=User)
def create_profile_for_new_user(sender, instance, created, **kwargs):
    if created:
        Profile.objects.get_or_create(user=instance)


@receiver(user_signed_up)
def link_referral_on_signup(request, user, **kwargs):
    """Fired by allauth right after a signup completes (username/password
    or Google). Looks for a referral code captured earlier in the session
    (see accounts/middleware.py) and, if valid, links the two accounts.

    No wallet credit happens here — see Profile.release_referral_bonus_if_due,
    called from Order.mark_paid(). Paying out at signup would reward fake
    accounts with no real behavior; paying out on a genuine first order is
    the actual signal that this was a real referral.
    """
    code = request.session.pop('referral_code', None)
    if not code:
        return

    referrer_profile = Profile.objects.filter(referral_code__iexact=code).exclude(user=user).first()
    if not referrer_profile:
        return

    new_user_profile, _ = Profile.objects.get_or_create(user=user)
    if new_user_profile.referred_by_id:
        return  # already attributed somehow — don't double-link

    new_user_profile.referred_by = referrer_profile.user
    new_user_profile.save(update_fields=['referred_by'])
