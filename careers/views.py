from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .models import JobApplication, JobListing


def job_list(request):
    jobs = JobListing.objects.filter(is_active=True)
    return render(request, 'careers/list.html', {'jobs': jobs})


def job_detail(request, slug):
    job = get_object_or_404(JobListing, slug=slug, is_active=True)
    return render(request, 'careers/detail.html', {'job': job})


@require_POST
def apply(request, slug):
    job = get_object_or_404(JobListing, slug=slug, is_active=True)
    full_name = request.POST.get('full_name', '').strip()
    email = request.POST.get('email', '').strip()
    phone_number = request.POST.get('phone_number', '').strip()

    if not (full_name and email and phone_number):
        messages.error(request, 'Please fill in your name, email, and phone number.')
        return redirect('careers:detail', slug=job.slug)

    JobApplication.objects.create(
        job=job, full_name=full_name, email=email, phone_number=phone_number,
        message=request.POST.get('message', '').strip(),
        resume_link=request.POST.get('resume_link', '').strip(),
    )
    messages.success(request, f'Application received for {job.title} — we\'ll be in touch!')
    return redirect('careers:detail', slug=job.slug)
