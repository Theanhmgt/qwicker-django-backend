from django.contrib import admin
from django.urls import path, re_path, include
from rest_framework import routers
from . import views

r = routers.DefaultRouter()

r.register('users', views.BasicUserViewSet)
r.register('shippers', views.ShipperViewSet)
r.register('shipper-more', views.ShipperMoreViewSet)
r.register('vehicles', views.VehicleViewSet)
r.register('products', views.ProductViewSet)
r.register('product-categories', views.ProductCategoryViewSet)
r.register('jobs', views.JobViewSet)
r.register('shipper-jobs', views.ShipperJobViewSet)
r.register('auction', views.AuctionViewSet)
r.register('shipment', views.ShipmentViewSet)
r.register('address', views.AddressViewSet)
r.register('payments', views.PaymentViewSet)
r.register('payment-method', views.PaymentMethodViewSet)
r.register('feedbacks', views.FeedbackViewSet)
r.register('account',views.AccountViewSet)
r.register('coupon',views.CouponViewSet)
urlpatterns = [
    path('', include(r.urls))
]
