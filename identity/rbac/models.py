from django.db import models


class Role(models.Model):
    """
    دور المستخدم (مثل: admin, instructor, student, reviewer ...)
    """
    name = models.CharField(max_length=150)
    slug = models.SlugField(unique=True)
    description = models.TextField(blank=True)

    def __str__(self):
        return self.name


class Permission(models.Model):
    """
    صلاحية محددة (مثل: course.view, course.manage, app.access ...)
    """
    code = models.CharField(max_length=100, unique=True)
    name = models.CharField(max_length=200)
    module = models.CharField(max_length=100, blank=True)
    description = models.TextField(blank=True)
    
    roles = models.ManyToManyField(
        Role,
        related_name="permissions",
        blank=True,
    )

    def __str__(self):
        return self.code
