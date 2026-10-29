"""Shared validation for HTML search, product API and local suggestions."""
import re
from decimal import Decimal

from django import forms
from django.core.exceptions import ValidationError


class PackPriceField(forms.DecimalField):
    def to_python(self, value):
        if value not in self.empty_values and not re.fullmatch(r"\d+(?:\.\d{1,2})?", str(value).strip()):
            raise ValidationError("Enter a PKR amount with at most two decimal places.")
        return super().to_python(value)


class OfferFilterForm(forms.Form):
    fresh = forms.ChoiceField(required=False, choices=(("", "Any check age"), ("0", "Any check age"), ("1", "Fresh only")))
    in_stock = forms.ChoiceField(required=False, choices=(("", "Any stock status"), ("0", "Any stock status"), ("1", "In stock only")))
    min_price = PackPriceField(label="Minimum pack price (PKR)", required=False, min_value=0,
        max_value=Decimal("9999999999.99"), max_digits=12, decimal_places=2,
        widget=forms.NumberInput(attrs={"step": "0.01", "min": "0", "placeholder": "No minimum"}))
    max_price = PackPriceField(label="Maximum pack price (PKR)", required=False, min_value=0,
        max_value=Decimal("9999999999.99"), max_digits=12, decimal_places=2,
        widget=forms.NumberInput(attrs={"step": "0.01", "min": "0", "placeholder": "No maximum"}))

    def clean_fresh(self):
        return self.cleaned_data["fresh"] == "1"

    def clean_in_stock(self):
        return self.cleaned_data["in_stock"] == "1"

    def clean(self):
        data = super().clean()
        low, high = data.get("min_price"), data.get("max_price")
        if low is not None and high is not None and low > high:
            self.add_error("max_price", "Maximum price must be at least the minimum price.")
        return data


class InvalidOfferFilters(ValueError):
    def __init__(self, form):
        self.errors = {key: [item["message"] for item in values]
                       for key, values in form.errors.get_json_data().items()}
        super().__init__("Correct the offer filters before searching.")


def offer_filters(params):
    form = OfferFilterForm(params)
    if not form.is_valid():
        raise InvalidOfferFilters(form)
    return form.cleaned_data


def filters_active(filters):
    return filters["fresh"] or filters["in_stock"] or any(filters[key] is not None for key in ("min_price", "max_price"))
