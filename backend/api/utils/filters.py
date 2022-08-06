from django_filters.rest_framework import CharFilter, FilterSet
from recipes.models import Ingredient, Recipe, Tag
from users.models import User


class IngredientFilter(FilterSet):
    name = CharFilter(lookup_expr='istartswith')

    class Meta:
        model = Ingredient
        fields = ('name',)


class TagFilter(FilterSet):
    tags = filter.ModelMultipleChoiceFilter(
        field_name='tags__slug',
        to_field_name='slug',
        queryset=Tag.objects.all()
    )
    author = filter.ModelChoiceFilter(queryset=User.objects.all())
    is_favorited = filter.BooleanFilter(method='get_is_favorited')
    is_in_shopping_cart = filter.BooleanFilter(
        method='get_is_in_shopping_cart'
    )

    class Meta:
        model = Recipe
        fields = ('tags', 'author', 'is_favorited', 'is_in_shopping_cart')

    def get_is_favorited(self, queryset, name, value):
        if bool(value) and not self.request.user.is_anonymous:
            return queryset.filter(
                recipes_favorite_related__user=self.request.user
            )
        return queryset

    def get_is_in_shopping_cart(self, queryset, name, value):
        if bool(value) and not self.request.user.is_anonymous:
            return queryset.filter(shoppingcartrecipe__user=self.request.user)
        return queryset.exclude(shoppingcartrecipe__user=self.request.user)
