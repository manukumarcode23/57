from quart import Blueprint, request, render_template, redirect, session
from bot.database import AsyncSessionLocal
from bot.models import Ticket
from bot.server.publisher.utils import require_publisher
from bot.server.security import csrf_protect, get_csrf_token
from sqlalchemy import select, and_, func
import logging

bp = Blueprint('publisher_tickets', __name__)
logger = logging.getLogger('bot.server')

@bp.route('/tickets')
@require_publisher
async def tickets():
    status_filter = request.args.get('status', 'all')
    
    async with AsyncSessionLocal() as db_session:
        query = select(Ticket).where(Ticket.publisher_id == session['publisher_id'])
        
        if status_filter != 'all':
            query = query.where(Ticket.status == status_filter)
        
        query = query.order_by(Ticket.created_at.desc())
        result = await db_session.execute(query)
        ticket_list = result.scalars().all()
        
        open_count = await db_session.scalar(
            select(func.count(Ticket.id)).where(
                and_(
                    Ticket.publisher_id == session['publisher_id'],
                    Ticket.status == 'open'
                )
            )
        )
        
        closed_count = await db_session.scalar(
            select(func.count(Ticket.id)).where(
                and_(
                    Ticket.publisher_id == session['publisher_id'],
                    Ticket.status == 'closed'
                )
            )
        )
        
    csrf_token = get_csrf_token()
    return await render_template('publisher_tickets.html',
                                  active_page='tickets',
                                  email=session['publisher_email'],
                                  tickets=ticket_list,
                                  status_filter=status_filter,
                                  open_count=open_count or 0,
                                  closed_count=closed_count or 0,
                                  csrf_token=csrf_token)

@bp.route('/tickets/create', methods=['POST'])
@require_publisher
@csrf_protect
async def create_ticket():
    data = await request.form
    subject = data.get('subject', '').strip()[:200]
    message = data.get('message', '').strip()[:5000]
    priority = data.get('priority', 'normal')
    
    if priority not in ['low', 'normal', 'high', 'urgent']:
        priority = 'normal'
    
    if not subject or not message:
        return redirect('/publisher/tickets?error=Subject and message are required')
    
    async with AsyncSessionLocal() as db_session:
        try:
            ticket = Ticket(
                publisher_id=session['publisher_id'],
                subject=subject,
                message=message,
                priority=priority,
                status='open'
            )
            db_session.add(ticket)
            await db_session.commit()
            
            logger.info(f"Ticket created by publisher {session['publisher_email']}: {subject}")
            
            return redirect('/publisher/tickets?success=Ticket created successfully')
        except Exception as e:
            await db_session.rollback()
            logger.error(f"Error creating ticket: {e}")
            return redirect('/publisher/tickets?error=Failed to create ticket')

@bp.route('/tickets/<int:ticket_id>')
@require_publisher
async def view_ticket(ticket_id):
    async with AsyncSessionLocal() as db_session:
        result = await db_session.execute(
            select(Ticket).where(
                and_(
                    Ticket.id == ticket_id,
                    Ticket.publisher_id == session['publisher_id']
                )
            )
        )
        ticket = result.scalar_one_or_none()
        
        if not ticket:
            return redirect('/publisher/tickets?error=Ticket not found')
        
    csrf_token = get_csrf_token()
    return await render_template('publisher_ticket_detail.html',
                                  active_page='tickets',
                                  email=session['publisher_email'],
                                  ticket=ticket,
                                  csrf_token=csrf_token)
