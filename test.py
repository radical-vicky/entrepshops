

@rider_required
def rider_dashboard(request, rider):
    now = timezone.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    
    # Base querysets
    rider_orders = rider.orders.select_related('delivery_address', 'user')
    
    # 1. New Orders (Paid but not assigned yet, or assigned to this rider as 'preparing')
    # Assuming 'PAID' means unassigned (available for pickup) and 'PREPARING' means accepted
    new_orders = rider_orders.filter(status=Order.Status.PAID)
    accepted_orders = rider_orders.filter(status=Order.Status.PREPARING)
    
    # 2. Ongoing Deliveries (Out for delivery)
    ongoing_orders = rider_orders.filter(status=Order.Status.OUT_FOR_DELIVERY)
    
    # 3. Completed Today
    completed_today = rider_orders.filter(
        status=Order.Status.DELIVERED,
        delivered_at__gte=today_start
    )
    
    # 4. Today's Earnings (Sum of delivery fees for completed orders today)
    # Assuming rider earns the delivery_fee. You can change this to a % of total if preferred.
    earnings_today = completed_today.aggregate(total_earned=Sum('delivery_fee'))['total_earned'] or 0
    
    # 5. Recent Deliveries (for the list)
    recent_deliveries = completed_today.order_by('-delivered_at')[:5]

    # 6. Update Rider Status (assuming you have a status field on the Rider model)
    # If you don't have a status field, you can add it to Rider: is_online = models.BooleanField(default=True)
    rider.is_active = True 
    
    context = {
        'rider': rider,
        'new_orders': new_orders,
        'accepted_orders': accepted_orders,
        'ongoing_orders': ongoing_orders,
        'completed_today': completed_today,
        'earnings_today': earnings_today,
        'recent_deliveries': recent_deliveries,
        'active_count': accepted_orders.count() + ongoing_orders.count(),
        'new_count': new_orders.count(),
    }
    
    return render(request, 'orders/rider_dashboard.html', context)