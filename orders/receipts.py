"""
Generates a printable PDF receipt for a paid order, using reportlab (pure
Python — no system libraries needed, so it works on serverless hosts like
Vercel without extra build steps).
"""
import io

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle


def generate_receipt_pdf(order):
    """Returns the receipt as raw PDF bytes."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        topMargin=22 * mm, bottomMargin=22 * mm, leftMargin=20 * mm, rightMargin=20 * mm,
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('ReceiptTitle', parent=styles['Title'], fontSize=20, spaceAfter=2)
    muted_style = ParagraphStyle('Muted', parent=styles['Normal'], textColor=colors.HexColor('#666666'))
    heading_style = ParagraphStyle('SectionHeading', parent=styles['Heading3'], spaceBefore=14, spaceAfter=6)

    elements = [
        Paragraph('DrinkShop', title_style),
        Paragraph('Receipt', muted_style),
        Spacer(1, 10 * mm),
    ]

    meta_rows = [
        ['Order', f'#{order.id}'],
        ['Status', order.get_status_display()],
        ['Date', order.created_at.strftime('%d %b %Y, %H:%M')],
        ['Customer', order.user.get_full_name() or order.user.username],
        ['Phone', order.phone_number],
        ['Delivery address', order.delivery_address.as_text()],
    ]
    meta_table = Table(meta_rows, colWidths=[45 * mm, 120 * mm])
    meta_table.setStyle(TableStyle([
        ('FONTSIZE', (0, 0), (-1, -1), 9.5),
        ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#666666')),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
    ]))
    elements.append(meta_table)

    elements.append(Paragraph('Items', heading_style))
    item_rows = [['Item', 'Unit price', 'Qty', 'Subtotal']]
    for item in order.items.all():
        item_rows.append([
            item.product.name,
            f'KES {item.unit_price:,.2f}',
            str(item.quantity),
            f'KES {item.subtotal:,.2f}',
        ])
    items_table = Table(item_rows, colWidths=[80 * mm, 35 * mm, 20 * mm, 30 * mm])
    items_table.setStyle(TableStyle([
        ('FONTSIZE', (0, 0), (-1, -1), 9.5),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('LINEBELOW', (0, 0), (-1, 0), 0.75, colors.HexColor('#222222')),
        ('LINEBELOW', (0, -1), (-1, -1), 0.5, colors.HexColor('#dddddd')),
        ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f7f7f7')]),
    ]))
    elements.append(items_table)
    elements.append(Spacer(1, 6 * mm))

    totals_rows = [
        ['Subtotal', f'KES {order.subtotal:,.2f}'],
        ['Delivery fee', f'KES {order.delivery_fee:,.2f}'],
        ['Total', f'KES {order.total:,.2f}'],
    ]
    totals_table = Table(totals_rows, colWidths=[135 * mm, 30 * mm])
    totals_table.setStyle(TableStyle([
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, -1), (-1, -1), 12),
        ('LINEABOVE', (0, -1), (-1, -1), 0.75, colors.HexColor('#222222')),
        ('TOPPADDING', (0, -1), (-1, -1), 6),
    ]))
    elements.append(totals_table)

    txn = order.mpesa_transactions.filter(status='success').order_by('-created_at').first()
    if txn and txn.mpesa_receipt_number:
        elements.append(Paragraph('Payment', heading_style))
        elements.append(Paragraph(
            f'Paid via M-Pesa &middot; Receipt No. {txn.mpesa_receipt_number} &middot; '
            f'{txn.phone_number}',
            muted_style,
        ))

    elements.append(Spacer(1, 14 * mm))
    elements.append(Paragraph(
        'Thank you for shopping with DrinkShop. Questions about this order? '
        'Reply to your order confirmation email.',
        muted_style,
    ))

    doc.build(elements)
    return buffer.getvalue()
