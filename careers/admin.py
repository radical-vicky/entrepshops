from django.contrib import admin

from .models import JobApplication, JobListing


class JobApplicationInline(admin.TabularInline):
    model = JobApplication
    extra = 0
    readonly_fields = ('full_name', 'email', 'phone_number', 'message', 'resume_link', 'submitted_at')
    fields = ('full_name', 'email', 'phone_number', 'resume_link', 'reviewed', 'submitted_at')


@admin.register(JobListing)
class JobListingAdmin(admin.ModelAdmin):
    list_display = ('title', 'department', 'location', 'employment_type', 'is_active', 'posted_at')
    list_filter = ('department', 'employment_type', 'is_active')
    search_fields = ('title', 'department', 'description')
    prepopulated_fields = {'slug': ('title',)}
    inlines = [JobApplicationInline]


@admin.register(JobApplication)
class JobApplicationAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'job', 'email', 'phone_number', 'reviewed', 'submitted_at')
    list_filter = ('reviewed', 'job')
    search_fields = ('full_name', 'email', 'phone_number')
