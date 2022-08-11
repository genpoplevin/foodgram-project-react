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

    def to_internal_value(self, data):
        return Tag.objects.get(id=data)


class IngredientSerializer(serializers.ModelSerializer):
    class Meta:
        model = Ingredient
        fields = ('id', 'name', 'measurement_unit')

    def update(self, instance, validated_data):
        instance.name = validated_data.get('name', instance.name)
        instance.measurement_unit = validated_data.get(
            'measurement_unit',
            instance.measurement_unit
        )
        instance.save()
        return instance

    def to_internal_value(self, data):
        return get_object_or_404(Ingredient, id=data)


class IngredientsInRecipeSerializer(serializers.ModelSerializer):
    id = serializers.PrimaryKeyRelatedField(queryset=Ingredient.objects.all())
    name = serializers.CharField(source='ingredient.name', read_only=True)
    measurement_unit = serializers.CharField(
        source='ingredient.measurement_unit',
        read_only=True
    )

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

    def get_is_favorited(self, obj):
        user = self.context.get('request').user
        if not user.is_authenticated:
            return False
        return Recipe.objects.filter(favorites__user=user, id=obj.id).exists()

    def get_is_in_shopping_cart(self, obj):
        user = self.context.get('request').user
        if not user.is_authenticated:
            return False
        return Recipe.objects.filter(
            shopping_cart__user=user,
            id=obj.id
        ).exists()

    def ingredints_create(self, ingredients, recipe):
        ingredients_list = [
            IngredientsInRecipe(
                ingredient=ingredient['id'],
                recipe=recipe,
                amount=ingredient['amount']
            ) for ingredient in ingredients
        ]
        IngredientsInRecipe.objects.bulk_create(ingredients_list)

    def validate(self, data):
        ingredients = data.get('ingredientsinrecipe_set')
        if not ingredients:
            raise serializers.ValidationError(
                {'errors': 'Добавьте хотя бы один ингредиент в рецепт'}
            )
        validated_ingredients = []
        for ingredient in ingredients:
            id = ingredient['id']
            amount = ingredient['amount']
            if amount <= 0:
                raise serializers.ValidationError(
                    {
                        'errors': ('Количество ингридиента должно быть '
                                   'больше 0')
                    }
                )
            validated_ingredients.append(id)
        if len(validated_ingredients) != len(ingredients):
            raise serializers.ValidationError(
                'Ингридиенты должны быть уникальными.'
            )
        tags = data['tags']
        if not tags:
            raise serializers.ValidationError(
                'В рецепте должен быть хотя бы один тег')
        for tag in tags:
            if not Tag.objects.filter(name=tag).exists():
                raise serializers.ValidationError(
                    'Такого тега нет в базе'
                )
        return data

    def create(self, validated_data):
        ingredients = validated_data.pop('ingredientsinrecipe_set')
        tags = validated_data.pop('tags')
        recipe = Recipe.objects.create(**validated_data)
        recipe.tags.set(tags)
        self.ingredints_create(
            ingredients=ingredients, recipe=recipe)
        return recipe


    def update(self, instance, validated_data):
        IngredientsInRecipe.objects.filter(recipe=instance).delete()
        tags = validated_data.pop('tags')
        ingredients = validated_data.pop('ingredientsinrecipe_set')
        instance.tags.set(tags)
        Recipe.objects.filter(pk=instance.pk).update(**validated_data)
        self.ingredints_create(
            ingredients=ingredients, recipe=instance)
        instance.refresh_from_db()
        return super().update(instance=instance, validated_data=validated_data)



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
