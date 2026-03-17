from django.urls import path
from .views import (
    GenerateEmailView, SendEmailView,
    CampaignListCreateView, CampaignDetailView,
    CampaignRecipientsView, CampaignRecipientDetailView,
    CampaignBulkSendView,
)

urlpatterns = [
    # Existing
    path("generate/", GenerateEmailView.as_view(), name="mail-generate"),
    path("send/",     SendEmailView.as_view(),     name="mail-send"),

    # Campaigns
    path("campaigns/",
         CampaignListCreateView.as_view(),      name="campaign-list"),
    path("campaigns/<int:pk>/",
         CampaignDetailView.as_view(),          name="campaign-detail"),
    path("campaigns/<int:pk>/recipients/",
         CampaignRecipientsView.as_view(),      name="campaign-recipients"),
    path("campaigns/<int:pk>/recipients/<int:rid>/",
         CampaignRecipientDetailView.as_view(), name="campaign-recipient-detail"),
    path("campaigns/<int:pk>/send/",
         CampaignBulkSendView.as_view(),        name="campaign-send"),
]
