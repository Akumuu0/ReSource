from decimal import Decimal

from django import forms

from accounts.models import Department

from .models import Asset, Category


class AssetForm(forms.ModelForm):
    """Register or edit an asset (C2). The department is set by the server."""

    class Meta:
        model = Asset
        fields = ["name", "description", "category", "condition", "tags",
                  "quantity", "estimated_value", "weight_kg", "repair_cost"]
        labels = {
            "estimated_value": "Value per unit (AED)",
            "weight_kg": "Weight per unit (kg)",
            "repair_cost": "Repair cost per unit (AED)",
            "tags": "Tags (comma-separated)",
        }
        help_texts = {
            "estimated_value": "What a new one would cost.",
            "repair_cost": "Expected repairs before reuse; 0 if none.",
        }
        widgets = {"description": forms.Textarea(attrs={"rows": 4})}

    def clean_quantity(self):
        quantity = self.cleaned_data["quantity"]
        if quantity < 1:
            raise forms.ValidationError("Quantity must be at least 1.")
        return quantity

    def clean_estimated_value(self):
        value = self.cleaned_data["estimated_value"]
        if value < 0:
            raise forms.ValidationError("The value cannot be negative.")
        return value

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["repair_cost"].required = False  # empty means no repairs

    def clean_repair_cost(self):
        cost = self.cleaned_data["repair_cost"] or Decimal("0")
        if cost < 0:
            raise forms.ValidationError("The repair cost cannot be negative.")
        return cost

    def clean_weight_kg(self):
        weight = self.cleaned_data["weight_kg"]
        if weight <= Decimal("0"):
            raise forms.ValidationError("The weight must be more than 0 kg.")
        return weight


class SearchForm(forms.Form):
    """Search and filter published assets (C3)."""

    q = forms.CharField(required=False, label="Keyword")
    category = forms.ModelChoiceField(queryset=Category.objects.all(), required=False, empty_label="Any category")
    condition = forms.ChoiceField(choices=[("", "Any condition")] + Asset.CONDITION_CHOICES, required=False)
    department = forms.ModelChoiceField(queryset=Department.objects.all(), required=False, empty_label="Any department")
