# pyrefly: ignore [missing-import]
from django.db import models

class PackageScan(models.Model):
    COURIER_CHOICES = [
        ('', 'Unknown'),
        ('amazon', 'Amazon'),
        ('delhivery', 'Delhivery'),
        ('bluedart', 'Blue Dart'),
        ('ekart', 'Ekart'),
        ('xpressbees', 'Xpressbees'),
        ('dtdc', 'DTDC'),
        ('shadowfax', 'Shadowfax'),
        ('other', 'Other'),
    ]
    
    CONDITION_CHOICES = [
        ('Good condition', 'Good condition'),
        ('Damage', 'Damage'),
    ]

    tracking_id = models.CharField(max_length=200)
    order_id = models.CharField(max_length=200, blank=True, default='')
    driver_name = models.CharField(max_length=100, blank=True, default='')
    courier = models.CharField(max_length=50, choices=COURIER_CHOICES, blank=True, default='Amazon')
    condition = models.CharField(max_length=50, choices=CONDITION_CHOICES, default='Good condition')
    notes = models.CharField(max_length=500, blank=True, default='')
    photo = models.ImageField(upload_to='package_photos/', blank=True, null=True)
    scanned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-scanned_at']

    def __str__(self):
        return f"{self.tracking_id} @ {self.scanned_at.strftime('%Y-%m-%d %H:%M:%S')}"
