# ===============================================================
#  mail/urls.py
#  URL routing for all mail features — one-on-one and bulk campaigns
#  Mounted under /api/mail/ in backend/urls.py
# ===============================================================


# ---------------- Step 0: Imports ----------------
from django.urls import path
from .views import (
    GenerateEmailView, SendEmailView,
    CampaignListCreateView, CampaignDetailView,
    CampaignRecipientsView, CampaignRecipientDetailView,
    CampaignBulkSendView,
)


urlpatterns = [

    # ---------------- Step 1: One-on-One Mail ----------------
    # POST → send a prompt + tone to LLaMA → returns {subject, body} draft
    path("generate/", GenerateEmailView.as_view(), name="mail-generate"),

    # POST → send a drafted email to a single recipient via Django's email backend
    path("send/",     SendEmailView.as_view(),     name="mail-send"),

    # ---------------- Step 2: Campaign Management ----------------
    # GET  → list all campaigns for the current user's company group
    # POST → create a new named campaign
    path("campaigns/",
         CampaignListCreateView.as_view(), name="campaign-list"),

    # GET    → fetch one campaign (includes recipients + draft)
    # PATCH  → update campaign name, subject, or body
    # DELETE → permanently delete the campaign and all its recipients
    path("campaigns/<int:pk>/",
         CampaignDetailView.as_view(), name="campaign-detail"),

    # ---------------- Step 3: Recipient Management ----------------
    # GET  → list all recipients in a campaign
    # POST → add recipients via JSON array or uploaded CSV/text file
    path("campaigns/<int:pk>/recipients/",
         CampaignRecipientsView.as_view(), name="campaign-recipients"),

    # PATCH  → update a recipient's display name
    # DELETE → remove a single recipient from the campaign
    path("campaigns/<int:pk>/recipients/<int:rid>/",
         CampaignRecipientDetailView.as_view(), name="campaign-recipient-detail"),

    # ---------------- Step 4: Bulk Send ----------------
    # POST → sends the saved draft to ALL recipients in the campaign
    #        Runs in a background thread so the API responds immediately
    path("campaigns/<int:pk>/send/",
         CampaignBulkSendView.as_view(), name="campaign-send"),
]