from django.db import models

class CalculationLog(models.Model):
    application_id = models.IntegerField()
    service_count = models.IntegerField()
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    calculated_at = models.DateTimeField(auto_now_add=True)
    token_used = models.CharField(max_length=255)
    
    class Meta:
        db_table = 'calculation_logs'