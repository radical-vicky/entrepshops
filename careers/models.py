from django.db import models
from django.urls import reverse
from django.utils.text import slugify


class JobListing(models.Model):
    class EmploymentType(models.TextChoices):
        FULL_TIME = 'full_time', 'Full-time'
        PART_TIME = 'part_time', 'Part-time'
        CONTRACT = 'contract', 'Contract'
        GIG = 'gig', 'Gig / per-delivery'

    title = models.CharField(max_length=150, help_text='e.g. "Delivery Rider", "Marketing Associate", "Operations Manager".')
    slug = models.SlugField(max_length=170, unique=True, blank=True)
    department = models.CharField(max_length=100, help_text='e.g. Riders, Marketing, Management, Customer Support.')
    location = models.CharField(max_length=100, default='Nairobi')
    employment_type = models.CharField(max_length=20, choices=EmploymentType.choices, default=EmploymentType.FULL_TIME)
    description = models.TextField(help_text='What the role involves.')
    requirements = models.TextField(blank=True, help_text='One requirement per line.')
    is_active = models.BooleanField(default=True, help_text='Turn off to stop accepting applications without deleting the listing.')
    posted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-posted_at']

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.title)
            slug = base_slug
            i = 1
            while JobListing.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                i += 1
                slug = f'{base_slug}-{i}'
            self.slug = slug
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse('careers:detail', args=[self.slug])

    @property
    def requirements_list(self):
        return [line.strip() for line in self.requirements.splitlines() if line.strip()]


class JobApplication(models.Model):
    job = models.ForeignKey(JobListing, related_name='applications', on_delete=models.CASCADE)
    full_name = models.CharField(max_length=150)
    email = models.EmailField()
    phone_number = models.CharField(max_length=20)
    message = models.TextField(blank=True, help_text='Cover note / why you\'re a fit.')
    resume_link = models.URLField(blank=True, help_text='Link to CV/portfolio (Google Drive, LinkedIn, etc.)')
    submitted_at = models.DateTimeField(auto_now_add=True)
    reviewed = models.BooleanField(default=False)

    class Meta:
        ordering = ['-submitted_at']

    def __str__(self):
        return f'{self.full_name} — {self.job.title}'
