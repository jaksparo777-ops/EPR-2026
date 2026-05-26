from django.db import models

class SoftDeleteQuerySet(models.QuerySet):
    def delete(self):
        # Soft delete bulk updates
        return super().update(is_deleted=True)

    def hard_delete(self):
        # Physical bulk delete
        return super().delete()

class SoftDeleteManager(models.Manager):
    def get_queryset(self):
        return SoftDeleteQuerySet(self.model, using=self._db).filter(is_deleted=False)

class SoftDeleteModel(models.Model):
    is_deleted = models.BooleanField(default=False)

    objects = SoftDeleteManager()
    all_objects = models.Manager()

    class Meta:
        abstract = True

    def delete(self, *args, **kwargs):
        self.is_deleted = True
        self.save(update_fields=['is_deleted'])

    def hard_delete(self, *args, **kwargs):
        super().delete(*args, **kwargs)
