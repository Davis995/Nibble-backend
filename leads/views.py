from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import F, Q, Count
from django.utils import timezone
from django.conf import settings
import random
import string

from .models import Lead, Notification, DemoSchedule, Onboarding, Logs
from .serializers import LeadSerializer, NotificationSerializer, DemoScheduleSerializer, OnboardingSerializer, LogsSerializer
from .utils import get_lead_frontend_urls, get_school_frontend_urls, get_demo_frontend_urls, get_onboarding_frontend_urls
from authentication.permissions import IsAdmin, IsEnterpriseUser
from schools.models import School, Student
from schools.serializers import SchoolSerializer
from authentication.models import User, Plan, Subscription
from django.core.cache import cache
from django.db.models import Count
from django.utils.dateparse import parse_datetime

User = get_user_model()


class SalesUsersListView(APIView):
    """
    GET: List users with roles sale_manager and sales_assistant
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not request.user.is_authenticated:
            return Response({'error': 'Access denied'}, status=status.HTTP_403_FORBIDDEN)
        qs = User.objects.filter(role__in=['sale_manager', 'sales_assistant'])
        users = []
        for u in qs:
            users.append({
                'id': str(u.id),
                'email': u.email,
                'full_name': f"{u.first_name} {u.last_name}".strip(),
                'role': u.role,
            })
        return Response({'success': True, 'data': {'users': users}}, status=status.HTTP_200_OK)


# ============================================================================
# LEAD CRUD VIEWS
# ============================================================================

class LeadListCreateView(APIView):
    """
    GET: List all leads (for admins/sales team)
    POST: Create new lead (anyone can create)
    """
    
    permission_classes = [AllowAny]  # Anyone can create leads

    def get(self, request):
        """List leads with search, filters, pagination and CSV export"""
        if not request.user.is_authenticated or not (request.user.role in ['sale_manager', 'sales_assistant'] or request.user.is_superuser):
            return Response({'error': 'Access denied'}, status=status.HTTP_403_FORBIDDEN)

        # Query parameters
        page = max(0, int(request.query_params.get('page', 0)))
        limit = int(request.query_params.get('limit', 10))
        limit = max(1, min(limit, 100))
        search = request.query_params.get('search')
        status_filter = request.query_params.get('status')
        staff_id = request.query_params.get('staffId')
        sort_by = request.query_params.get('sortBy', 'lastActivity')
        sort_order = request.query_params.get('sortOrder', 'desc')

        qs = Lead.objects.filter(is_deleted=False)
        if search:
            from django.db.models import Q
            qs = qs.filter(
                Q(institution_name__icontains=search) |
                Q(firstname__icontains=search) |
                Q(secondname__icontains=search) |
                Q(workemail__icontains=search)
            )
        if status_filter:
            qs = qs.filter(status__in=[s.strip() for s in status_filter.split(',')])
        if staff_id:
            qs = qs.filter(assigned_staff__id=staff_id)

        # sorting
        sort_map = {
            'schoolName': 'institution_name',
            'status': 'status',
            'createdAt': 'created_at',
            'lastActivity': 'updated_at'
        }
        sort_field = sort_map.get(sort_by, 'updated_at')
        if sort_order == 'desc':
            sort_field = f"-{sort_field}"
        qs = qs.order_by(sort_field)

        total = qs.count()
        start = page * limit
        end = start + limit
        leads = qs[start:end]

        serializer = LeadSerializer(leads, many=True)
        items = []
        for item in serializer.data:
            items.append({
                'id': str(item['id']),
                'schoolName': item.get('institution_name'),
                'contactPerson': f"{item.get('firstname')} {item.get('secondname')}",
                'email': item.get('workemail'),
                'phone': item.get('phonenumber'),
                'status': item.get('status'),
                'assignedStaffId': str(item.get('assigned_staff')) if item.get('assigned_staff') else None,
                'assignedStaff': item.get('assigned_staff_name'),
                'country': item.get('country'),
                'studentCount': None,
                'lastActivity': item.get('last_activity').isoformat() if item.get('last_activity') else item.get('updated_at'),
                'createdAt': item.get('created_at'),
                'updatedAt': item.get('updated_at'),
                'frontend_urls': get_lead_frontend_urls(item['id'])
            })

        response = {
            'success': True,
            'data': {
                'leads': items,
                'pagination': {
                    'page': page,
                    'limit': limit,
                    'total': total,
                    'totalPages': (total + limit - 1) // limit if limit else 0
                }
            }
        }

        return Response(response)

    def post(self, request):
        """Create new lead"""
        serializer = LeadSerializer(data=request.data)
        if serializer.is_valid():
            with transaction.atomic():
                lead = serializer.save()
                
                # Create log
                Logs.objects.create(
                    lead=lead,
                    log_type='lead_created',
                    description=f"Lead created for {lead.firstname} {lead.secondname} from {lead.institution_name}"
                )
                
                # Send welcome email to lead
                self._send_lead_welcome_email(lead)
                
                # Create notification for sales manager
                sales_managers = User.objects.filter(role='sale_manager')
                for manager in sales_managers:
                    Notification.objects.create(
                        user=manager,
                        notification_type='new_lead',
                        title=f"New Lead: {lead.institution_name}",
                        body=f"New lead created: {lead.firstname} {lead.secondname} from {lead.institution_name}. Please review and assign.",
                        priority='high'
                    )
                
                return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def _send_lead_welcome_email(self, lead):
        """Send welcome email to lead"""
        subject = f"Welcome to Our Platform - {lead.institution_name}"
        html_message = render_to_string('leads/lead_welcome.html', {'lead': lead})
        plain_message = strip_tags(html_message)
        from_email = settings.DEFAULT_FROM_EMAIL
        to = lead.workemail
        
        send_mail(subject, plain_message, from_email, [to], html_message=html_message)


class LeadExportCSVView(APIView):
    """GET: Export filtered leads to CSV"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not request.user.is_authenticated:
            return Response({'error': 'Access denied'}, status=status.HTTP_403_FORBIDDEN)

        # reuse filtering logic from list view
        search = request.query_params.get('search')
        status_filter = request.query_params.get('status')
        staff_id = request.query_params.get('staffId')

        qs = Lead.objects.filter(is_deleted=False)
        if search:
            from django.db.models import Q
            qs = qs.filter(
                Q(institution_name__icontains=search) |
                Q(firstname__icontains=search) |
                Q(secondname__icontains=search) |
                Q(workemail__icontains=search)
            )
        if status_filter:
            qs = qs.filter(status__in=[s.strip() for s in status_filter.split(',')])
        if staff_id:
            qs = qs.filter(assigned_staff__id=staff_id)

        # build CSV
        import csv
        from django.http import HttpResponse

        response = HttpResponse(content_type='text/csv; charset=utf-8')
        filename = f"leads_{timezone.now().date().isoformat()}.csv"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'

        writer = csv.writer(response)
        writer.writerow(["School Name","Contact Person","Email","Phone","Status","Assigned Staff","Country","Student Count","Last Activity"])
        for l in qs:
            last_log = l.logs.order_by('-created_at').first()
            last_activity = last_log.created_at.isoformat() if last_log else l.updated_at.isoformat()
            writer.writerow([
                l.institution_name,
                f"{l.firstname} {l.secondname}",
                l.workemail,
                l.phonenumber,
                l.status,
                l.assigned_staff.get_full_name() if l.assigned_staff else '',
                l.country,
                '',
                last_activity
            ])
        return response


class LeadDetailView(APIView):
    """
    GET: Get lead details
    PUT: Update lead
    DELETE: Delete lead
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, lead_id):
        """Get lead details"""
        try:
            lead = Lead.objects.get(id=lead_id)
            # Check permissions
            if not self._can_access_lead(request.user, lead):
                return Response({'error': 'Access denied'}, status=status.HTTP_403_FORBIDDEN)
            
            serializer = LeadSerializer(lead)
            data = serializer.data
            data['frontend_urls'] = get_lead_frontend_urls(lead_id)
            return Response(data)
        except Lead.DoesNotExist:
            return Response({'error': 'Lead not found'}, status=status.HTTP_404_NOT_FOUND)

    def put(self, request, lead_id):
        """Update lead"""
        try:
            lead = Lead.objects.get(id=lead_id)
            if not self._can_access_lead(request.user, lead):
                return Response({'error': 'Access denied'}, status=status.HTTP_403_FORBIDDEN)
            
            old_status = lead.status
            serializer = LeadSerializer(lead, data=request.data, partial=True)
            if serializer.is_valid():
                lead = serializer.save()
                
                # Log status changes
                if old_status != lead.status:
                    Logs.objects.create(
                        lead=lead,
                        user=request.user,
                        log_type='lead_assigned' if lead.status == 'contacted' else 'demo_scheduled',
                        description=f"Lead status changed from {old_status} to {lead.status}"
                    )
                
                return Response(serializer.data)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        except Lead.DoesNotExist:
            return Response({'error': 'Lead not found'}, status=status.HTTP_404_NOT_FOUND)

    def delete(self, request, lead_id):
        """Delete lead"""
        try:
            lead = Lead.objects.get(id=lead_id)
            if not self._can_access_lead(request.user, lead):
                return Response({'error': 'Access denied'}, status=status.HTTP_403_FORBIDDEN)

            # Soft delete
            lead.is_deleted = True
            lead.deleted_at = timezone.now()
            lead.save()
            return Response({'success': True, 'data': {'id': str(lead.id), 'message': 'Lead successfully deleted', 'deletedAt': lead.deleted_at.isoformat()}}, status=status.HTTP_200_OK)
        except Lead.DoesNotExist:
            return Response({'success': False, 'error': {'code': 'LEAD_NOT_FOUND', 'message': 'Lead not found or already deleted'}}, status=status.HTTP_404_NOT_FOUND)

    def _can_access_lead(self, user, lead):
        """Check if user can access this lead"""
        if user.is_superuser or user.role == 'sale_manager':
            return True
        if user.role == 'sales_assistant':
            return lead.assigned_staff == user or lead.assigned_staff is None
        return False


class LeadAssignView(APIView):
    """
    POST: Assign lead to sales assistant
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, lead_id):
        """Assign lead"""
        if request.user.role not in ['sale_manager', 'sales_assistant'] and not request.user.is_superuser:
            return Response({'error': 'Only sales managers or sales assistants can assign leads'}, status=status.HTTP_403_FORBIDDEN)
        
        try:
            lead = Lead.objects.get(id=lead_id)
        except Lead.DoesNotExist:
            return Response({'error': 'Lead not found'}, status=status.HTTP_404_NOT_FOUND)
        
        assigned_user_id = request.data.get('assigned_user_id')
        if not assigned_user_id:
            return Response({'error': 'assigned_user_id required'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            assigned_user = User.objects.get(id=assigned_user_id, role__in=['sale_manager', 'sales_assistant'])
        except User.DoesNotExist:
            return Response({'error': 'Invalid assignee; must be sale_manager or sales_assistant'}, status=status.HTTP_404_NOT_FOUND)
        
        with transaction.atomic():
            lead.assigned_staff = assigned_user
            lead.status = 'contacted'
            lead.save()
            
            # Create log
            Logs.objects.create(
                lead=lead,
                user=request.user,
                log_type='lead_assigned',
                description=f"Lead assigned to {assigned_user.username}"
            )
            
            # Create notification
            Notification.objects.create(
                user=assigned_user,
                title=f"Lead Assigned: {lead.institution_name}",
                body=f"You have been assigned a lead: {lead.firstname} {lead.secondname} from {lead.institution_name}. Please schedule a demo."
            )
            
            # Send email
            self._send_assignment_email(lead, assigned_user)
            
            return Response({'success': True, 'data': {'message': 'Lead assigned successfully'}})
        
    def _send_assignment_email(self, lead, assigned_user):
        """Send assignment email"""
        subject = f"New Lead Assigned: {lead.institution_name}"
        html_message = render_to_string('leads/lead_assigned.html', {'lead': lead, 'assigned_user': assigned_user})
        plain_message = strip_tags(html_message)
        from_email = settings.DEFAULT_FROM_EMAIL
        to = assigned_user.email
        
        send_mail(subject, plain_message, from_email, [to], html_message=html_message)


class LeadConvertView(APIView):
    """
    POST: Convert lead to school
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, lead_id):
        """Convert lead to school"""
        if request.user.role not in ['sale_manager', 'sales_assistant'] and not request.user.is_superuser:
            return Response({'error': 'Access denied'}, status=status.HTTP_403_FORBIDDEN)
        
        try:
            lead = Lead.objects.get(id=lead_id)
        except Lead.DoesNotExist:
            return Response({'error': 'Lead not found'}, status=status.HTTP_404_NOT_FOUND)
        
        if lead.status != 'negotiated':
            return Response({'error': 'Lead must be in negotiated status to convert'}, status=status.HTTP_400_BAD_REQUEST)
        
        with transaction.atomic():
            # Create school
            school = School.objects.create(
                name=lead.institution_name,
                school_email=lead.workemail,
                max_students=100,  # Default
            )
            
            # Create admin user
            password = self._generate_password()
            admin_user = User.objects.create_user(
                username=f"{lead.firstname}{lead.secondname}@{school.school_email.split('@')[1]}",
                email=school.school_email,
                password=password,
                first_name=lead.firstname,
                last_name=lead.secondname,
                user_type='enterprise',
                organisation=school,
                role='school_admin'
            )
            school.admin_user = admin_user
            school.save()
            
            # Create subscription (basic plan)
            plan = Plan.objects.filter(use_type='enterprise').first()
            if plan:
                subscription = Subscription.objects.create(
                    plan=plan,
                    organisation=school,
                    max_users=plan.max_users or 50,
                    start_credits=plan.total_credits,
                    remaining_credits=plan.total_credits,
                    billing_start_date=timezone.now().date(),
                    billing_end_date=timezone.now().date() + timezone.timedelta(days=30),
                    status='active'
                )
                school.subscription = subscription
                school.save()
            
            # Create onboarding
            onboarding = Onboarding.objects.create(
                school=school,
                onboarding_manager=request.user,
                startdate=timezone.now().date(),
                expected_go_live_date=timezone.now().date() + timezone.timedelta(days=30),
                onboarding_type='online',
                percentage=0
            )
            
            # Update lead
            lead.status = 'converted'
            lead.save()
            
            # Create logs
            Logs.objects.create(
                lead=lead,
                user=request.user,
                log_type='lead_converted',
                description=f"Lead converted to school: {school.name}"
            )
            
            # Send emails
            self._send_conversion_email(lead, school, admin_user, password)
            self._send_onboarding_email(onboarding, admin_user)
            
            return Response({
                'success': True,
                'message': 'Lead converted to school successfully',
                'school': SchoolSerializer(school).data,
                'frontend_urls': get_school_frontend_urls(school.id),
                'admin_credentials': {
                    'username': admin_user.username,
                    'email': admin_user.email,
                    'temporary_password': password
                }
            })
        
    def _generate_password(self):
        """Generate random password"""
        return ''.join(random.choices(string.ascii_letters + string.digits, k=12))
    
    def _send_conversion_email(self, lead, school, admin_user, password):
        """Send conversion email with login details"""
        subject = f"Welcome to Our Platform - {school.name}"
        html_message = render_to_string('leads/school_created.html', {
            'lead': lead,
            'school': school,
            'admin_user': admin_user,
            'password': password
        })
        plain_message = strip_tags(html_message)
        from_email = 'noreply@yourcompany.com'
        to = admin_user.email
        
        send_mail(subject, plain_message, from_email, [to], html_message=html_message)
    
    def _send_onboarding_email(self, onboarding, admin_user):
        """Send onboarding email"""
        subject = f"Onboarding Started - {onboarding.school.name}"
        html_message = render_to_string('leads/onboarding_started.html', {
            'onboarding': onboarding,
            'admin_user': admin_user
        })
        plain_message = strip_tags(html_message)
        from_email = 'noreply@yourcompany.com'
        to = admin_user.email
        
        send_mail(subject, plain_message, from_email, [to], html_message=html_message)


# ============================================================================
# DEMO SCHEDULE CRUD VIEWS
# ============================================================================

class DemoScheduleListCreateView(APIView):
    """
    GET: List demo schedules
    POST: Create demo schedule
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """List demo schedules with pagination, filtering, and search"""
        if request.user.role in ['sale_manager', 'sales_assistant'] or request.user.is_superuser:
            schedules = DemoSchedule.objects.all().order_by('-created_at')
        else:
            schedules = DemoSchedule.objects.filter(lead__assigned_staff=request.user).order_by('-created_at')
        
        # Filter by status
        status_filter = request.query_params.get('status')
        if status_filter:
            schedules = schedules.filter(demo_status__in=[s.strip() for s in status_filter.split(',')])
        
        # Search by school name
        search = request.query_params.get('search')
        if search:
            schedules = schedules.filter(lead__institution_name__icontains=search)
        
        # Filter by staff
        staff_id = request.query_params.get('staffId')
        if staff_id:
            schedules = schedules.filter(assigned_staff__id=staff_id)
        
        # Pagination
        page = max(1, int(request.query_params.get('page', 1)))
        page_size = 7
        total_count = schedules.count()
        start = (page - 1) * page_size
        end = start + page_size
        
        paginated_schedules = schedules[start:end]
        serializer = DemoScheduleSerializer(paginated_schedules, many=True)
        data = serializer.data
        
        # Add frontend URLs to each demo
        for item in data:
            item['frontend_urls'] = get_demo_frontend_urls(item['id'])
        
        total_pages = (total_count + page_size - 1) // page_size
        return Response({
            'data': data,
            'pagination': {
                'page': page,
                'page_size': page_size,
                'total_count': total_count,
                'total_pages': total_pages
            }
        })


    def post(self, request):
        """Create demo schedule"""
        lead_id = request.data.get('lead')
        if not lead_id:
            return Response({'error': 'lead is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            lead = Lead.objects.get(id=lead_id)
        except Lead.DoesNotExist:
            return Response({'error': 'Lead not found'}, status=status.HTTP_404_NOT_FOUND)
        
        # Check permissions
        if not (request.user == lead.assigned_staff or request.user.role in ['sale_manager', 'sales_assistant'] or request.user.is_superuser):
            return Response({'error': 'Access denied'}, status=status.HTTP_403_FORBIDDEN)
        
        serializer = DemoScheduleSerializer(data=request.data)
        if serializer.is_valid():
            with transaction.atomic():
                # validate assigned_staff role if provided
                assigned_id = request.data.get('assigned_staff') or request.data.get('assignedStaff') or request.data.get('assignedStaffId')
                if assigned_id:
                    try:
                        assignee = User.objects.get(id=assigned_id)
                        if assignee.role not in ['sale_manager', 'sales_assistant']:
                            return Response({'error': 'Assigned staff must be sale_manager or sales_assistant'}, status=status.HTTP_400_BAD_REQUEST)
                    except User.DoesNotExist:
                        return Response({'error': 'Assigned staff not found'}, status=status.HTTP_404_NOT_FOUND)

                schedule = serializer.save()
                
                # Update lead status
                lead.status = 'demo_scheduled'
                lead.save()
                
                # Create log
                Logs.objects.create(
                    lead=lead,
                    user=request.user,
                    log_type='demo_scheduled',
                    description=f"Demo scheduled for {schedule.date} at {schedule.time}"
                )
                
                # Send email to lead
                self._send_demo_email(lead, schedule)
                
                return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    def _send_demo_email(self, lead, schedule):
        """Send demo scheduling email"""
        subject = f"Demo Scheduled - {lead.institution_name}"
        html_message = render_to_string('leads/demo_scheduled.html', {
            'lead': lead,
            'schedule': schedule
        })
        plain_message = strip_tags(html_message)
        from_email = 'noreply@yourcompany.com'
        to = lead.workemail
        
        send_mail(subject, plain_message, from_email, [to], html_message=html_message)


class DemoScheduleDetailView(APIView):
    """
    GET: Get demo schedule
    PUT: Update demo schedule
    DELETE: Delete demo schedule
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, schedule_id):
        """Get demo schedule"""
        try:
            schedule = DemoSchedule.objects.get(id=schedule_id)
            if not self._can_access_schedule(request.user, schedule):
                return Response({'error': 'Access denied'}, status=status.HTTP_403_FORBIDDEN)
            
            serializer = DemoScheduleSerializer(schedule)
            data = serializer.data
            data['frontend_urls'] = get_demo_frontend_urls(schedule_id)
            return Response(data)
        except DemoSchedule.DoesNotExist:
            return Response({'error': 'Demo schedule not found'}, status=status.HTTP_404_NOT_FOUND)

    def put(self, request, schedule_id):
        """Update demo schedule"""
        try:
            schedule = DemoSchedule.objects.get(id=schedule_id)
            if not self._can_access_schedule(request.user, schedule):
                return Response({'error': 'Access denied'}, status=status.HTTP_403_FORBIDDEN)
            
            serializer = DemoScheduleSerializer(schedule, data=request.data, partial=True)
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        except DemoSchedule.DoesNotExist:
            return Response({'error': 'Demo schedule not found'}, status=status.HTTP_404_NOT_FOUND)

    def delete(self, request, schedule_id):
        """Delete demo schedule"""
        try:
            schedule = DemoSchedule.objects.get(id=schedule_id)
            if not self._can_access_schedule(request.user, schedule):
                return Response({'error': 'Access denied'}, status=status.HTTP_403_FORBIDDEN)
            
            # mark as cancelled
            schedule.demo_status = 'cancelled'
            schedule.save()
            return Response({'success': True, 'message': 'Demo cancelled successfully'})
        except DemoSchedule.DoesNotExist:
            return Response({'error': 'Demo schedule not found'}, status=status.HTTP_404_NOT_FOUND)

    def _can_access_schedule(self, user, schedule):
        """Check if user can access this schedule"""
        if user.is_superuser or user.role == 'sale_manager':
            return True
        return schedule.assigned_staff == user or schedule.lead.assigned_staff == user


class DemoStatusUpdateView(APIView):
    """PATCH: Update demo status (completed/missed/cancelled)"""
    permission_classes = [IsAuthenticated]

    def patch(self, request, schedule_id):
        try:
            schedule = DemoSchedule.objects.get(id=schedule_id)
        except DemoSchedule.DoesNotExist:
            return Response({'success': False, 'error': {'code': 'DEMO_NOT_FOUND', 'message': 'Demo not found'}}, status=status.HTTP_404_NOT_FOUND)

        if request.user.role not in ['sale_manager', 'sales_assistant'] and not request.user.is_superuser:
            return Response({'success': False, 'error': {'code': 'PERMISSION_DENIED', 'message': 'Access denied'}}, status=status.HTTP_403_FORBIDDEN)

        new_status = request.data.get('status')
        allowed = ['scheduled', 'completed', 'missed', 'cancelled']
        if new_status not in allowed:
            return Response({'success': False, 'error': {'code': 'INVALID_STATUS', 'message': 'Invalid demo status'}}, status=status.HTTP_400_BAD_REQUEST)

        schedule.demo_status = new_status
        schedule.save()

        # optional feedback logging
        feedback = request.data.get('feedback')
        if feedback:
            Logs.objects.create(lead=schedule.lead, user=request.user, log_type='demo_feedback', description=feedback)

        return Response({'success': True, 'data': {'id': schedule.id, 'status': schedule.demo_status, 'updatedAt': schedule.updated_at.isoformat()}})


class DemosCalendarView(APIView):
    """GET: Calendar view for demos"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        year = int(request.query_params.get('year', timezone.now().year))
        month = int(request.query_params.get('month', timezone.now().month))
        staff_id = request.query_params.get('staffId')

        qs = DemoSchedule.objects.filter(date__year=year, date__month=month)
        if staff_id:
            qs = qs.filter(assigned_staff__id=staff_id)

        from calendar import monthrange
        days = []
        _, last_day = monthrange(year, month)
        for d in range(1, last_day+1):
            date_obj = timezone.datetime(year, month, d).date()
            day_demos = qs.filter(date=date_obj)
            demos_list = []
            for s in day_demos:
                demos_list.append({'id': s.id, 'time': s.time.strftime('%H:%M'), 'schoolName': s.lead.institution_name if s.lead else None, 'status': s.demo_status, 'assignedStaff': s.assigned_staff.get_full_name() if s.assigned_staff else None})
            days.append({'date': date_obj.isoformat(), 'dayOfWeek': date_obj.strftime('%A'), 'demos': demos_list})

        return Response({'success': True, 'data': {'year': year, 'month': month, 'days': days}})


class DemosUpcomingView(APIView):
    """GET: upcoming demos"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        days = int(request.query_params.get('days', 7))
        staff_id = request.query_params.get('staffId')
        today = timezone.localdate()
        end = today + timezone.timedelta(days=days)

        qs = DemoSchedule.objects.filter(date__gte=today, date__lte=end)
        if staff_id:
            qs = qs.filter(assigned_staff__id=staff_id)

        upcoming = []
        for s in qs.order_by('date','time'):
            scheduled_at = timezone.datetime.combine(s.date, s.time)
            if timezone.is_naive(scheduled_at):
                scheduled_at = timezone.make_aware(scheduled_at)
            days_until = (s.date - today).days
            upcoming.append({'id': s.id, 'leadId': s.lead.id if s.lead else None, 'schoolName': s.lead.institution_name if s.lead else None, 'scheduledAt': scheduled_at.isoformat(), 'meetingLink': s.meeting_link, 'assignedStaff': s.assigned_staff.get_full_name() if s.assigned_staff else None, 'assignedStaffId': s.assigned_staff.id if s.assigned_staff else None, 'status': s.demo_status, 'daysUntil': days_until, 'isToday': days_until==0})

        return Response({'success': True, 'data': {'upcoming': upcoming, 'total': len(upcoming)}})


class DemoAttendeesView(APIView):
    """POST: add attendee placeholder (model not implemented)"""
    permission_classes = [IsAuthenticated]

    def post(self, request, schedule_id):
        try:
            schedule = DemoSchedule.objects.get(id=schedule_id)
        except DemoSchedule.DoesNotExist:
            return Response({'success': False, 'error': {'code': 'DEMO_NOT_FOUND', 'message': 'Demo not found'}}, status=status.HTTP_404_NOT_FOUND)

        name = request.data.get('name')
        email = request.data.get('email')
        role = request.data.get('role')
        if not name or not email:
            return Response({'success': False, 'error': {'code': 'VALIDATION_ERROR', 'message': 'name and email required'}}, status=status.HTTP_400_BAD_REQUEST)

        # Since attendees model isn't implemented, return a mocked attendee id and echo
        attendee = {'id': f"att-{int(timezone.now().timestamp())}", 'name': name, 'email': email, 'role': role or '', 'status': 'invited'}
        return Response({'success': True, 'data': {'id': schedule_id, 'attendees': [attendee]}})


# ============================================================================
# NOTIFICATION CRUD VIEWS
# ============================================================================

class NotificationListView(APIView):
    """GET: List user's own notifications with filtering and unread count (user-specific only)"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """List user's own notifications with unread and priority filtering"""
        unread_filter = request.query_params.get('unread')
        priority = request.query_params.get('priority')
        limit = int(request.query_params.get('limit', 50))

        # Filter by current user only - users can only see their own notifications
        qs = Notification.objects.filter(user=request.user).order_by('-created_at')
        if unread_filter and unread_filter.lower() == 'true':
            qs = qs.filter(is_read=False)
        if priority:
            qs = qs.filter(priority__iexact=priority)

        notifications = qs[:limit]
        unread_count = Notification.objects.filter(user=request.user, is_read=False).count()

        serializer = NotificationSerializer(notifications, many=True)
        return Response({'success': True, 'data': {'notifications': serializer.data, 'unreadCount': unread_count}})


class LeadStatusUpdateView(APIView):
    """PATCH: Update lead status"""
    permission_classes = [IsAuthenticated]

    def patch(self, request, lead_id):
        try:
            lead = Lead.objects.get(id=lead_id, is_deleted=False)
        except Lead.DoesNotExist:
            return Response({'success': False, 'error': {'code': 'LEAD_NOT_FOUND', 'message': 'Lead not found'}}, status=status.HTTP_404_NOT_FOUND)

        new_status = request.data.get('status')
        reason = request.data.get('reason')
        allowed = [c[0] for c in Lead.STATUS_CHOICES]
        if new_status not in allowed:
            return Response({'success': False, 'error': {'code': 'INVALID_STATUS', 'message': 'Invalid status value', 'details': f"Status must be one of: {', '.join(allowed)}"}}, status=status.HTTP_400_BAD_REQUEST)

        if new_status == 'lost' and not reason:
            return Response({'success': False, 'error': {'code': 'INVALID_STATUS', 'message': 'reason required when marking lost'}}, status=status.HTTP_400_BAD_REQUEST)

        previous = lead.status
        lead.status = new_status
        lead.save()

        # Log the change
        Logs.objects.create(
            lead=lead,
            user=request.user,
            log_type='status_change',
            description=f"Status changed from {previous} to {new_status}. {('Reason: ' + reason) if reason else ''}"
        )

        return Response({'success': True, 'data': {'id': str(lead.id), 'status': lead.status, 'previousStatus': previous, 'changedAt': timezone.now().isoformat(), 'changedBy': request.user.get_full_name(), 'message': f"Status successfully updated from {previous} to {lead.status}"}})


class LeadAddNoteView(APIView):
    """POST: Add note to lead timeline (implemented as a Log entry)"""
    permission_classes = [IsAuthenticated]

    def post(self, request, lead_id):
        content = request.data.get('content')
        note_type = request.data.get('type', 'default')
        if not content or not content.strip():
            return Response({'success': False, 'error': {'code': 'VALIDATION_ERROR', 'message': 'content is required'}}, status=status.HTTP_400_BAD_REQUEST)

        try:
            lead = Lead.objects.get(id=lead_id, is_deleted=False)
        except Lead.DoesNotExist:
            return Response({'success': False, 'error': {'code': 'LEAD_NOT_FOUND', 'message': 'Lead not found'}}, status=status.HTTP_404_NOT_FOUND)

        log = Logs.objects.create(
            lead=lead,
            user=request.user,
            log_type='note',
            description=content,
            metadata={'type': note_type}
        )

        return Response({'success': True, 'data': {'id': str(log.id), 'leadId': str(lead.id), 'content': log.description, 'type': note_type, 'author': request.user.get_full_name(), 'createdAt': log.created_at.isoformat()}}, status=status.HTTP_201_CREATED)


class NotificationMarkReadView(APIView):
    """PATCH: Mark notification as read (user-specific)"""
    permission_classes = [IsAuthenticated]

    def patch(self, request, notification_id):
        """Mark user's notification as read"""
        try:
            # Verify notification belongs to current user
            notification = Notification.objects.get(id=notification_id, user=request.user)
            notification.is_read = True
            notification.save()
            return Response({'success': True, 'data': {'id': notification.id, 'read': True}})
        except Notification.DoesNotExist:
            return Response({'success': False, 'error': 'Notification not found'}, status=status.HTTP_404_NOT_FOUND)


class UnreadNotificationsView(APIView):
    """GET: Retrieve all unread notifications for the current user"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """
        Get all unread notifications for the authenticated user.
        Optional query parameters:
        - priority: filter by priority level (low, medium, high)
        - limit: maximum number of notifications to return (default: 50)
        - offset: pagination offset (default: 0)
        """
        priority = request.query_params.get('priority')
        limit = int(request.query_params.get('limit', 50))
        offset = int(request.query_params.get('offset', 0))

        # Ensure reasonable limits
        limit = max(1, min(limit, 100))
        offset = max(0, offset)

        # Get unread notifications for current user, ordered by creation date
        qs = Notification.objects.filter(
            user=request.user,
            is_read=False
        ).order_by('-created_at')

        # Apply priority filter if provided
        if priority:
            allowed_priorities = ['low', 'medium', 'high']
            if priority.lower() in allowed_priorities:
                qs = qs.filter(priority__iexact=priority)

        # Get total count before pagination
        total_count = qs.count()

        # Apply pagination
        unread_notifications = qs[offset:offset + limit]

        serializer = NotificationSerializer(unread_notifications, many=True)
        
        return Response({
            'success': True,
            'data': {
                'notifications': serializer.data,
                'total': total_count,
                'count': len(serializer.data),
                'limit': limit,
                'offset': offset
            }
        }, status=status.HTTP_200_OK)


# ============================================================================
# ONBOARDING CRUD VIEWS
# ============================================================================

class OnboardingListView(APIView):
    """
    GET: List onboardings
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """List onboardings"""
        if request.user.role in ['sale_manager', 'sales_assistant'] or request.user.is_superuser:
            onboardings = Onboarding.objects.all().order_by('-created_at')
        else:
            onboardings = Onboarding.objects.filter(onboarding_manager=request.user).order_by('-created_at')
        
        serializer = OnboardingSerializer(onboardings, many=True)
        data = serializer.data
        
        # Add frontend URLs to each onboarding
        for item in data:
            item['frontend_urls'] = get_onboarding_frontend_urls(item['id'])
        
        return Response(data)


class OnboardingDetailView(APIView):
    """
    GET: Get onboarding
    PUT: Update onboarding
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, onboarding_id):
        """Get onboarding"""
        try:
            onboarding = Onboarding.objects.get(id=onboarding_id)
            if not self._can_access_onboarding(request.user, onboarding):
                return Response({'error': 'Access denied'}, status=status.HTTP_403_FORBIDDEN)
            
            serializer = OnboardingSerializer(onboarding)
            data = serializer.data
            data['frontend_urls'] = get_onboarding_frontend_urls(onboarding_id)
            return Response(data)
        except Onboarding.DoesNotExist:
            return Response({'error': 'Onboarding not found'}, status=status.HTTP_404_NOT_FOUND)

    def put(self, request, onboarding_id):
        """Update onboarding"""
        try:
            onboarding = Onboarding.objects.get(id=onboarding_id)
            if not self._can_access_onboarding(request.user, onboarding):
                return Response({'error': 'Access denied'}, status=status.HTTP_403_FORBIDDEN)
            
            old_status = onboarding.status
            serializer = OnboardingSerializer(onboarding, data=request.data, partial=True)
            if serializer.is_valid():
                onboarding = serializer.save()
                
                # Handle status changes
                if old_status != onboarding.status:
                    if onboarding.status == 'completed':
                        self._handle_onboarding_completion(onboarding)
                    elif onboarding.status == 'onhold':
                        self._send_onboarding_hold_email(onboarding)
                
                return Response(serializer.data)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        except Onboarding.DoesNotExist:
            return Response({'error': 'Onboarding not found'}, status=status.HTTP_404_NOT_FOUND)

    def _can_access_onboarding(self, user, onboarding):
        """Check if user can access this onboarding"""
        if user.is_superuser or user.role in ['sale_manager', 'sales_assistant']:
            return True
        return onboarding.onboarding_manager == user

    def _handle_onboarding_completion(self, onboarding):
        """Handle onboarding completion"""
        # Update school as live
        school = onboarding.school
        school.is_active = True
        school.save()
        
        # Send completion email
        self._send_onboarding_completion_email(onboarding)
        
        # Create log
        Logs.objects.create(
            log_type='school_live',
            description=f"School {school.name} is now live"
        )

    def _send_onboarding_completion_email(self, onboarding):
        """Send onboarding completion email"""
        subject = f"Onboarding Completed - {onboarding.school.name}"
        html_message = render_to_string('leads/onboarding_completed.html', {'onboarding': onboarding})
        plain_message = strip_tags(html_message)
        from_email = 'noreply@yourcompany.com'
        to = onboarding.school.admin_user.email
        
        send_mail(subject, plain_message, from_email, [to], html_message=html_message)
    
    def _send_onboarding_hold_email(self, onboarding):
        """Send onboarding on hold email"""
        subject = f"Onboarding On Hold - {onboarding.school.name}"
        html_message = render_to_string('leads/onboarding_onhold.html', {'onboarding': onboarding})
        plain_message = strip_tags(html_message)
        from_email = 'noreply@yourcompany.com'
        to = onboarding.school.admin_user.email
        
        send_mail(subject, plain_message, from_email, [to], html_message=html_message)


# ============================================================================
# LOGS CRUD VIEWS
# ============================================================================

class LogsListView(APIView):
    """
    GET: List logs
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """List logs"""
        if request.user.is_superuser or request.user.role in ['sale_manager', 'sales_assistant']:
            logs = Logs.objects.all().order_by('-created_at')
        else:
            logs = Logs.objects.filter(user=request.user).order_by('-created_at')
        
        serializer = LogsSerializer(logs, many=True)
        return Response(serializer.data)


# ============================================================================
# DASHBOARD VIEWS
# ============================================================================


class DashboardKPIView(APIView):
    """GET: Retrieve dashboard KPI data"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        # Allow caching for 5 minutes
        cache_key = f"dashboard_kpi:{request.user.id}:{request.query_params.get('dateRange','month')}"
        cached = cache.get(cache_key)
        if cached:
            return Response({'success': True, 'data': cached})

        date_range = request.query_params.get('dateRange', 'month')
        now = timezone.now()

        # total leads
        total_leads = Lead.objects.count()

        # converted leads
        converted_count = Lead.objects.filter(status__in=['converted']).count()
        conversion_rate = int((converted_count / total_leads * 100) if total_leads else 0)

        # schools onboarding
        schools_onboarding = Onboarding.objects.filter(status__in=['inprogress']).count()

        # upcoming demos today
        today = timezone.localdate()
        upcoming_demos_today = DemoSchedule.objects.filter(date=today).count()

        # simple trend calculations: compare current period count to previous same-length period
        def get_period_counts(model, date_field, period):
            if period == 'today':
                start = now.date()
                prev_start = start - timezone.timedelta(days=1)
                end = start
                prev_end = prev_start
            elif period == 'week':
                start = now.date() - timezone.timedelta(days=now.weekday())
                prev_start = start - timezone.timedelta(days=7)
                end = start + timezone.timedelta(days=6)
                prev_end = prev_start + timezone.timedelta(days=6)
            elif period == 'year':
                start = now.date().replace(month=1, day=1)
                prev_start = start.replace(year=start.year - 1)
                end = start.replace(month=12, day=31)
                prev_end = prev_start.replace(month=12, day=31)
            else:  # month
                start = now.date().replace(day=1)
                prev_month = (start - timezone.timedelta(days=1)).replace(day=1)
                prev_start = prev_month
                end = (start + timezone.timedelta(days=32)).replace(day=1) - timezone.timedelta(days=1)
                prev_end = (prev_start + timezone.timedelta(days=32)).replace(day=1) - timezone.timedelta(days=1)

            cur_count = model.objects.filter(created_at__date__gte=start, created_at__date__lte=end).count()
            prev_count = model.objects.filter(created_at__date__gte=prev_start, created_at__date__lte=prev_end).count()
            return cur_count, prev_count

        leads_cur, leads_prev = get_period_counts(Lead, 'created_at', date_range)
        demos_cur, demos_prev = get_period_counts(DemoSchedule, 'created_at', date_range)
        onboard_cur, onboard_prev = get_period_counts(Onboarding, 'created_at', date_range)

        def trend(cur, prev):
            if prev == 0:
                return cur
            return int(((cur - prev) / prev) * 100)

        leads_trend = trend(leads_cur, leads_prev)
        conversion_trend = trend(converted_count, converted_count - 1) if converted_count else 0
        onboarding_trend = trend(onboard_cur, onboard_prev)
        demos_trend = trend(demos_cur, demos_prev)

        data = {
            'totalLeads': total_leads,
            'conversionRate': conversion_rate,
            'schoolsOnboarding': schools_onboarding,
            'upcomingDemosToday': upcoming_demos_today,
            'leadsTrend': leads_trend,
            'conversionTrend': conversion_trend,
            'onboardingTrend': onboarding_trend,
            'demosTrend': demos_trend,
            'lastUpdated': timezone.now().isoformat()
        }

        cache.set(cache_key, data, 300)
        return Response({'success': True, 'data': data})


class DashboardLeadsStatusView(APIView):
    """GET: Breakdown of leads by status"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        cache_key = 'dashboard_leads_status'
        cached = cache.get(cache_key)
        if cached:
            return Response({'success': True, 'data': cached})

        totals = Lead.objects.values('status').annotate(count=Count('id'))
        total = Lead.objects.count()
        chart_data = []
        for t in totals:
            percentage = int((t['count'] / total) * 100) if total else 0
            chart_data.append({'status': t['status'], 'count': t['count'], 'percentage': percentage})

        data = {'chartData': chart_data, 'total': total}
        cache.set(cache_key, data, 300)
        return Response({'success': True, 'data': data})


class DashboardUpcomingDemosView(APIView):
    """GET: Get demos scheduled for today and upcoming days"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        days = int(request.query_params.get('days', 7))
        today = timezone.localdate()
        end = today + timezone.timedelta(days=days)

        demos = DemoSchedule.objects.filter(date__gte=today, date__lte=end).order_by('date', 'time')
        results = []
        for d in demos:
            scheduled_at = timezone.datetime.combine(d.date, d.time)
            scheduled_at = timezone.make_aware(scheduled_at) if timezone.is_naive(scheduled_at) else scheduled_at
            results.append({
                'id': str(d.id),
                'leadId': str(d.lead.id) if d.lead else None,
                'schoolName': getattr(d.lead, 'institution_name', None),
                'scheduledAt': scheduled_at.isoformat(),
                'meetingLink': d.meeting_link,
                'assignedStaff': d.assigned_staff.get_full_name() if d.assigned_staff else None,
                'assignedStaffId': str(d.assigned_staff.id) if d.assigned_staff else None,
                'status': 'scheduled',
                'notes': d.meeting_link or d.place or ''
            })

        data = {'demos': results, 'total': demos.count()}
        return Response({'success': True, 'data': data})


class DashboardActivityView(APIView):
    """GET: Get recent activities and updates"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        limit = int(request.query_params.get('limit', 10))
        cache_key = f"dashboard_activity:{limit}"
        cached = cache.get(cache_key)
        if cached:
            return Response({'success': True, 'data': cached})

        activities = []
        logs = Logs.objects.order_by('-created_at')[:limit]
        ICON_MAP = {
            'lead_created': 'plus',
            'demo_scheduled': 'calendar',
            'lead_assigned': 'user',
            'lead_converted': 'check',
            'onboarding_completed': 'flag',
        }
        COLOR_MAP = {
            'lead_created': 'info',
            'demo_scheduled': 'success',
            'lead_assigned': 'primary',
            'lead_converted': 'success',
            'onboarding_completed': 'success',
        }

        for l in logs:
            activity = {
                'id': str(l.id),
                'type': l.log_type,
                'description': l.description,
                'staffName': l.user.get_full_name() if l.user else 'System',
                'timestamp': l.created_at.isoformat(),
                'entityId': str(l.lead.id) if l.lead else None,
                'entityType': 'lead' if l.lead else None,
                'icon': ICON_MAP.get(l.log_type, 'activity'),
                'color': COLOR_MAP.get(l.log_type, 'info')
            }
            activities.append(activity)

        data = {'activities': activities, 'total': len(activities)}
        cache.set(cache_key, data, 60)
        return Response({'success': True, 'data': data})


# ============================================================================
# ACTIVITY & ANALYTICS VIEWS
# ============================================================================


class ActivityListView(APIView):
    """GET: List activities (logs) with pagination and filtering"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        page = max(0, int(request.query_params.get('page', 0)))
        limit = int(request.query_params.get('limit', 20))
        limit = max(1, min(limit, 100))
        activity_type = request.query_params.get('type')
        date_from = request.query_params.get('dateFrom')
        date_to = request.query_params.get('dateTo')

        qs = Logs.objects.all().order_by('-created_at')
        if activity_type:
            qs = qs.filter(log_type__iexact=activity_type)
        if date_from:
            try:
                start = timezone.datetime.fromisoformat(date_from).date()
                qs = qs.filter(created_at__date__gte=start)
            except Exception:
                pass
        if date_to:
            try:
                end = timezone.datetime.fromisoformat(date_to).date()
                qs = qs.filter(created_at__date__lte=end)
            except Exception:
                pass

        total = qs.count()
        start_idx = page * limit
        logs = qs[start_idx:start_idx + limit]

        ICON_MAP = {'lead_created': 'plus', 'demo_scheduled': 'calendar', 'lead_assigned': 'user', 'lead_converted': 'check', 'onboarding_completed': 'flag'}
        COLOR_MAP = {'lead_created': 'info', 'demo_scheduled': 'success', 'lead_assigned': 'primary', 'lead_converted': 'success', 'onboarding_completed': 'success'}

        activities = []
        for log in logs:
            activities.append({
                'id': str(log.id),
                'type': log.log_type,
                'description': log.description,
                'staffName': log.user.get_full_name() if log.user else 'System',
                'timestamp': log.created_at.isoformat(),
                'entityId': str(log.lead.id) if log.lead else None,
                'entityType': 'lead' if log.lead else None,
                'icon': ICON_MAP.get(log.log_type, 'activity'),
                'color': COLOR_MAP.get(log.log_type, 'info')
            })

        return Response({'success': True, 'data': {'activities': activities, 'pagination': {'page': page, 'limit': limit, 'total': total, 'totalPages': (total + limit - 1) // limit if limit else 0}}})


class AnalyticsView(APIView):
    """GET: Analytics data with summary, trends, and top performers"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        cache_key = 'analytics_data'
        cached = cache.get(cache_key)
        if cached:
            return Response({'success': True, 'data': cached})

        date_from = request.query_params.get('dateFrom')
        date_to = request.query_params.get('dateTo')

        # Date range filtering
        start_date = None
        end_date = None
        if date_from:
            try:
                start_date = timezone.datetime.fromisoformat(date_from).date()
            except Exception:
                pass
        if date_to:
            try:
                end_date = timezone.datetime.fromisoformat(date_to).date()
            except Exception:
                pass

        # Build querysets
        qs = Lead.objects.filter(is_deleted=False)
        if start_date:
            qs = qs.filter(created_at__date__gte=start_date)
        if end_date:
            qs = qs.filter(created_at__date__lte=end_date)

        total_leads = qs.count()
        this_month_start = timezone.now().date().replace(day=1)
        new_leads_this_month = qs.filter(created_at__date__gte=this_month_start).count()
        converted = qs.filter(status='converted').count()
        conversion_rate = int((converted / total_leads) * 100) if total_leads else 0

        # Leads by status
        leads_by_status = list(qs.values('status').annotate(count=Count('id')).order_by('-count'))

        # Leads by country
        leads_by_country = list(qs.values('country').annotate(count=Count('id')).order_by('-count')[:10])

        # Top performers (by leads assigned)
        top_performers = list(Lead.objects.filter(assigned_staff__isnull=False).values(staff_id=F('assigned_staff__id'), staff_name=F('assigned_staff__first_name')).annotate(leads_converted=Count('id', filter=Q(status='converted')), total=Count('id')).order_by('-leads_converted')[:5])
        for perf in top_performers:
            perf['conversionRate'] = int((perf.get('leads_converted', 0) / perf.get('total', 1)) * 100) if perf.get('total') else 0
            perf['staffId'] = str(perf.pop('staff_id', None))
            perf['staffName'] = perf.pop('staff_name', None)
            perf['leadsConverted'] = perf.pop('leads_converted', 0)

        # Trend data (last 3 months)
        from datetime import timedelta
        labels = []
        leads_trend = []
        conversions_trend = []
        for i in range(2, -1, -1):
            month_date = (timezone.now().date().replace(day=1) - timedelta(days=i*30)).replace(day=1)
            labels.append(month_date.strftime('%b'))
            month_leads = qs.filter(created_at__date__gte=month_date, created_at__date__lt=month_date + timedelta(days=32)).count()
            month_conversions = qs.filter(created_at__date__gte=month_date, created_at__date__lt=month_date + timedelta(days=32), status='converted').count()
            leads_trend.append(month_leads)
            conversions_trend.append(month_conversions)

        # Conversion time data - analyze time to conversion for converted leads
        converted_leads = Lead.objects.filter(status='converted', is_deleted=False)
        conversion_time_ranges = {
            '0-7 days': 0,
            '8-14 days': 0,
            '15-30 days': 0,
            '31-60 days': 0,
            '61+ days': 0
        }
        
        for lead in converted_leads:
            if lead.created_at and lead.updated_at:
                days_to_convert = (lead.updated_at.date() - lead.created_at.date()).days
                if days_to_convert <= 7:
                    conversion_time_ranges['0-7 days'] += 1
                elif days_to_convert <= 14:
                    conversion_time_ranges['8-14 days'] += 1
                elif days_to_convert <= 30:
                    conversion_time_ranges['15-30 days'] += 1
                elif days_to_convert <= 60:
                    conversion_time_ranges['31-60 days'] += 1
                else:
                    conversion_time_ranges['61+ days'] += 1
        
        conversion_time_data = [
            {'range': '0-7 days', 'count': conversion_time_ranges['0-7 days']},
            {'range': '8-14 days', 'count': conversion_time_ranges['8-14 days']},
            {'range': '15-30 days', 'count': conversion_time_ranges['15-30 days']},
            {'range': '31-60 days', 'count': conversion_time_ranges['31-60 days']},
            {'range': '61+ days', 'count': conversion_time_ranges['61+ days']}
        ]

        # Onboarding data - breakdown by status
        onboarding_statuses = Onboarding.objects.values('status').annotate(count=Count('id'))
        onboarding_data = []
        status_colors = {
            'inprogress': '#60A5FA',
            'completed': '#34D399',
            'onhold': '#F97316'
        }
        for status_item in onboarding_statuses:
            status_name_map = {'inprogress': 'In Progress', 'completed': 'Completed', 'onhold': 'On Hold'}
            onboarding_data.append({
                'name': status_name_map.get(status_item['status'], status_item['status']),
                'value': status_item['count'],
                'fill': status_colors.get(status_item['status'], '#9CA3AF')
            })

        data = {
            'summary': {
                'totalLeads': total_leads,
                'newLeadsThisMonth': new_leads_this_month,
                'conversion': {'rate': conversion_rate, 'count': converted, 'trend': 0},
                'revenue': {'annual': 0, 'monthly': 0, 'trend': 0}
            },
            'leadsByStatus': leads_by_status,
            'leadsByCountry': leads_by_country,
            'topPerformers': top_performers,
            'conversionTimeData': conversion_time_data,
            'onboardingData': onboarding_data,
            'trendData': {'labels': labels, 'leads': leads_trend, 'conversions': conversions_trend, 'revenue': [0, 0, 0]}
        }
        cache.set(cache_key, data, 300)
        return Response({'success': True, 'data': data})
