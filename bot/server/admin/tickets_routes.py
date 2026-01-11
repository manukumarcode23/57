from quart import Blueprint, request, render_template, redirect
from bot.database import AsyncSessionLocal
from bot.models import Ticket, Publisher
from sqlalchemy import select, func
from datetime import datetime, timezone
from .utils import require_admin
from bot.server.security import csrf_protect, get_csrf_token

bp = Blueprint('admin_tickets', __name__)

@bp.route('/tickets')
@require_admin
async def tickets():
    status_filter = request.args.get('status', 'all')
    
    async with AsyncSessionLocal() as db_session:
        query = select(Ticket).order_by(Ticket.created_at.desc())
        
        if status_filter != 'all':
            query = query.where(Ticket.status == status_filter)
        
        result = await db_session.execute(query)
        ticket_list = result.scalars().all()
        
        ticket_data = []
        for ticket in ticket_list:
            publisher_result = await db_session.execute(
                select(Publisher).where(Publisher.id == ticket.publisher_id)
            )
            publisher = publisher_result.scalar_one_or_none()
            
            ticket_data.append({
                'ticket': ticket,
                'publisher': publisher
            })
        
        open_count = await db_session.scalar(
            select(func.count(Ticket.id)).where(Ticket.status == 'open')
        )
        
        closed_count = await db_session.scalar(
            select(func.count(Ticket.id)).where(Ticket.status == 'closed')
        )
        
    return await render_template('admin_tickets.html',
                                  active_page='tickets',
                                  ticket_data=ticket_data,
                                  status_filter=status_filter,
                                  open_count=open_count or 0,
                                  closed_count=closed_count or 0)

@bp.route('/tickets/<int:ticket_id>')
@require_admin
async def view_ticket(ticket_id):
    async with AsyncSessionLocal() as db_session:
        result = await db_session.execute(
            select(Ticket).where(Ticket.id == ticket_id)
        )
        ticket = result.scalar_one_or_none()
        
        if not ticket:
            return redirect('/admin/tickets')
        
        publisher_result = await db_session.execute(
            select(Publisher).where(Publisher.id == ticket.publisher_id)
        )
        publisher = publisher_result.scalar_one_or_none()
        
    csrf_token = get_csrf_token()
    return await render_template('admin_ticket_detail.html',
                                  active_page='tickets',
                                  ticket=ticket,
                                  publisher=publisher,
                                  csrf_token=csrf_token)

@bp.route('/tickets/reply/<int:ticket_id>', methods=['POST'])
@require_admin
@csrf_protect
async def reply_ticket(ticket_id):
    data = await request.form
    admin_reply = data.get('admin_reply', '').strip()
    new_status = data.get('status', 'open')
    
    if not admin_reply:
        return redirect(f'/admin/tickets/{ticket_id}?error=Reply cannot be empty')
    
    async with AsyncSessionLocal() as db_session:
        try:
            result = await db_session.execute(
                select(Ticket).where(Ticket.id == ticket_id)
            )
            ticket = result.scalar_one_or_none()
            
            if not ticket:
                return redirect('/admin/tickets?error=Ticket not found')
            
            ticket.admin_reply = admin_reply
            ticket.status = new_status
            ticket.replied_at = datetime.now(timezone.utc)
            
            await db_session.commit()
            
            return redirect(f'/admin/tickets/{ticket_id}?success=Reply sent successfully')
        except Exception as e:
            await db_session.rollback()
            return redirect(f'/admin/tickets/{ticket_id}?error=Failed to send reply')
