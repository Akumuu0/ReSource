from django.contrib import admin

from .models import AIReport, CategoryValue, SustainabilityImpact

admin.site.register(CategoryValue)
admin.site.register(AIReport)
admin.site.register(SustainabilityImpact)
