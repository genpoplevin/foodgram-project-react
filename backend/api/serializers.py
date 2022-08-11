from django.shortcuts import get_object_or_404
from djoser.serializers import UserSerializer as DjoserUserSerializer
from drf_extra_fields.fields import Base64ImageField
from recipes.models import Favorite, Ingredient, IngredientsInRecipe, Recipe, ShoppingCart, Tag
from rest_framework import serializers
from users.models import Subscribe, User


class UserSerializer(DjoserUserSerializer):
    is_subscribed = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ('email', 'id', 'username', 'first_name', 'last_name',
                  'is_subscribed')

    def get_is_subscribed(self, obj):
        user = self.context.get('request').user
        if not user.is_authenticated:
            return False
        return user.follower.filter(author=obj).exists()


class TagSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tag
        fields = '__all__'

    def update(self, instance, validated_data):
        instance.name = validated_data.get('name', instance.name)
        instance.color = validated_data.get('color', instance.color)
        instance.slug = validated_data.get('slug', instance.slug)
        instance.save()
        return instance


class IngredientSerializer(serializers.ModelSerializer):
    class Meta:
        model = Ingredient
        fields = '__all__'

    def update(self, instance, validated_data):
        instance.name = validated_data.get('name', instance.name)
        instance.measurement_unit = validated_data.get(
            'measurement_unit',
            instance.measurement_unit
        )
        instance.save()
        return instance


class IngredientsInRecipeSerializer(serializers.ModelSerializer):
    id = IngredientSerializer()
    name = serializers.CharField(required=False)
    measurement_unit = serializers.CharField(required=False)
    amount = serializers.IntegerField()

    class Meta:
        model = IngredientsInRecipe
        fields = ('id', 'name', 'amount', 'measurement_unit')

    def to_representation(self, instance):
        data = IngredientSerializer(instance.ingredient).data
        data['amount'] = instance.amount
        return data


class RecipeSerializer(serializers.ModelSerializer):
    image = Base64ImageField()
    tags = TagSerializer(many=True)
    author = UserSerializer(read_only=True)
    ingredients = IngredientsInRecipeSerializer(
        source='ingredientsinrecipe_set',
        many=True
    )
    is_favorited = serializers.SerializerMethodField()
    is_in_shopping_cart = serializers.SerializerMethodField()

    class Meta:
        model = Recipe
        fields = ('id', 'tags', 'author', 'ingredients', 'is_favorited',
                  'is_in_shopping_cart', 'name', 'image', 'text',
                  'cooking_time')

    def ingredint_in_recipe_bulk_create(self, ingredients, recipe):
        ingredients_in_recipe = [
            IngredientsInRecipe(
                ingredient=ingredient['id'],
                recipe=recipe,
                amount=ingredient['amount']
            ) for ingredient in ingredients
        ]
        IngredientsInRecipe.objects.bulk_create(ingredients_in_recipe)

    def get_is_favorited(self, obj):
        request = self.context['request']
        if request is None or request.user.is_anonymous:
            return False
        return Favorite.objects.filter(
            user=request.user, recipe=obj).exists()

    def get_is_in_shopping_cart(self, obj):
        request = self.context.get('request')
        if request.user.is_anonymous:
            return False
        return ShoppingCart.objects.filter(
            user=request.user, recipe=obj).exists()

    def create(self, validated_data):
        ingredients = validated_data.pop('ingredientsinrecipe_set')
        tags = validated_data.pop('tags')
        recipe = Recipe.objects.create(**validated_data)
        recipe.tags.set(tags)

        self.ingredint_in_recipe_bulk_create(
            ingredients=ingredients, recipe=recipe)
        return recipe

    def update(self, instance, validated_data):
        IngredientsInRecipe.objects.filter(recipe=instance).delete()
        tags = validated_data.pop('tags')
        ingredients = validated_data.pop('ingredientsinrecipe_set')
        instance.tags.set(tags)
        Recipe.objects.filter(pk=instance.pk).update(**validated_data)

        self.ingredint_in_recipe_bulk_create(
            ingredients=ingredients, recipe=instance)

        instance.refresh_from_db()
        return super().update(instance=instance, validated_data=validated_data)

    def validate(self, data):
        if not data:
            raise serializers.ValidationError(
                'Обязательное поле.'
            )
        if len(data) < 1:
            raise serializers.ValidationError(
                'Не переданы ингредиенты.'
            )
        if 'ingredientsinrecipe' in data:
            ingredients = data.get('ingredientsinrecipe_set')
            uniq_ingredients = set()
            for ingredient in ingredients:
                id = ingredient['id']
                amount = ingredient['amount']
                if amount <= 0:
                    raise serializers.ValidationError(
                        'Минимальное количество ингредиента: 1'
                    )
                uniq_ingredients.add(id)

            if len(uniq_ingredients) != len(ingredients):
                raise serializers.ValidationError(
                    'Ингридиенты должны быть уникальными.'
                )
        return data


class RecipeSubscribesSerializer(serializers.ModelSerializer):
    image = Base64ImageField()

    class Meta:
        model = Recipe
        fields = ('id', 'name', 'image', 'cooking_time')
        read_only_fields = ('id', 'name', 'image', 'cooking_time')


class SubscribeSerializer(UserSerializer):
    id = serializers.ReadOnlyField(source='author.id')
    email = serializers.ReadOnlyField(source='author.email')
    username = serializers.ReadOnlyField(source='author.username')
    first_name = serializers.ReadOnlyField(source='author.first_name')
    last_name = serializers.ReadOnlyField(source='author.last_name')
    is_subscribed = serializers.SerializerMethodField()
    recipes = serializers.SerializerMethodField()
    recipes_count = serializers.SerializerMethodField()

    class Meta:
        model = Subscribe
        fields = ('email', 'id', 'username', 'first_name', 'last_name',
                  'is_subscribed', 'recipes', 'recipes_count')

    def get_is_subscribed(self, obj):
        return Subscribe.objects.filter(
            user=obj.user, author=obj.author
        ).exists()

    def get_recipes(self, obj):
        queryset = Recipe.objects.filter(author=obj.author)
        return RecipeSubscribesSerializer(queryset, many=True).data

    def get_recipes_count(self, obj):
        return Recipe.objects.filter(author=obj.author).count()


class FavoriteCartSerializer(serializers.ModelSerializer):
    name = serializers.ReadOnlyField(source='recipe.name')
    image = Base64ImageField(source='recipe.image')
    cooking_time = serializers.ReadOnlyField(source='recipe.cooking_time')

    class Meta:
        model = Recipe
        fields = ('id', 'name', 'image', 'cooking_time')
        read_only_fields = ('id', 'name', 'image', 'cooking_time')
