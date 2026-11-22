from django import forms

from assets.models import Asset, Category

from .models import Request

# HTML date inputs need the ISO format (YYYY-MM-DD) to show a value.
DATE_INPUT = forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"})


class RequestForm(forms.Form):
    """Request a listed asset (C4)."""

    quantity = forms.IntegerField(min_value=1)
    purpose = forms.CharField(widget=forms.Textarea(attrs={"rows": 3}))
    needed_by = forms.DateField(widget=DATE_INPUT, label="Needed by")


class NeedForm(forms.Form):
    """Describe a need; the AI then suggests matching assets (AI-2, design mockup 7.2)."""

    category = forms.ModelChoiceField(queryset=Category.objects.all())
    purpose = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 2}),
        help_text="What you need and what for, e.g. 'Two oscilloscopes for the teaching lab'.",
    )
    quantity = forms.IntegerField(min_value=1)
    needed_by = forms.DateField(widget=DATE_INPUT, label="Needed by")
    urgency = forms.ChoiceField(choices=Request.URGENCY_CHOICES, initial=Request.MEDIUM)
    min_condition = forms.ChoiceField(choices=[("", "Any")] + Asset.CONDITION_CHOICES, required=False,
                                      label="Minimum condition")
    specifications = forms.CharField(required=False, max_length=200,
                                     help_text="Minimums, e.g. 'At least 70 MHz, 2 channels'.")


class ReasonForm(forms.Form):
    """A reason, required to decline, reject or reject all matches."""

    reason = forms.CharField(max_length=255)


class ReceiptForm(forms.Form):
    """Confirm receipt with the condition on arrival (FR-4.10)."""

    condition = forms.ChoiceField(choices=Asset.CONDITION_CHOICES, label="Condition on arrival")
