"""
URL configuration for tomsuz_pos project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.shortcuts import redirect

urlpatterns = [
    path('admin/', admin.site.urls),
    
    # 1. Add your app URLs here
    path('products/', include('products.urls')),
    path('sales/', include('sales.urls')),
    path('accounts/', include('accounts.urls')), # <--- ADD THIS LINE
    
    # 2. This handles the "Empty" home page (redirects to the dashboard)
    path('', lambda request: redirect('sales:main_dashboard', permanent=False)),
]
