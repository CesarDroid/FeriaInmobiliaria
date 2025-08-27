from django.db import models

class Sale(models.Model):
    # Básicos
    agent_name = models.CharField(max_length=100)
    company = models.CharField(max_length=100)
    property_type = models.CharField(max_length=50)
    location = models.CharField(max_length=100)
    price = models.DecimalField(max_digits=12, decimal_places=2)
    commission = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    
    # Metadata
    sale_date = models.DateField(auto_now_add=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    # Opcional
    client_name = models.CharField(max_length=100, blank=True)
    notes = models.TextField(blank=True)

    def __str__(self):
        return f"{self.agent_name} - {self.property_type} - ${self.price}"