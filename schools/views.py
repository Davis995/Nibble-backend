from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, serializers
import pandas as pd
import random
import string

from .models import School, Student
from .serializers import SchoolSerializer, StudentSerializer, StaffCRUDSerializer, ActivitySerializer
from .permissions import IsSchoolAdminOrOperator, IsOwnerLevel, IsSchoolStaffOrAdmin
from .models import Invitation, Staff, Activity, UsageLog
from .serializers import InvitationSerializer, AcceptInvitationSerializer
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.conf import settings
from django.core.mail import send_mail, EmailMultiAlternatives
from django.template.loader import render_to_string
import uuid as _uuid
from .service import (
    ensure_user_slots_available,
    is_subscription_active_for_user_or_org,
)
from tools.models import AILog, AITool
from authentication.models import Subscription, Plan, CreditTop
from datetime import timedelta
from django.db.models import Count, Sum, Q
from django.db.models.functions import TruncMonth, TruncDay
from django.db import IntegrityError
from rest_framework.permissions import IsAuthenticated, AllowAny
from authentication.models import Plan, Subscription
from leads.models import Onboarding
from leads.models import DemoSchedule as LeadDemoSchedule


# ============================================================================
# SCHOOL CRUD VIEWS
# ============================================================================

class SchoolListCreateView(APIView):
    """
    GET: List all schools (for admins/operators)
    POST: Create new school (operators/superusers only)
    """
    # Use JWT auth for normal users, SSO for SSO requests
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """List all schools with pagination/filters"""
        # allow sale managers and sales assistants to view lists
        if not (request.user.is_superuser or request.user.role in ['sale_manager', 'sales_assistant', 'operator']):
            return Response({'error': 'Access denied'}, status=status.HTTP_403_FORBIDDEN)

        page = int(request.query_params.get('page', 0))
        limit = int(request.query_params.get('limit', 50))
        limit = max(1, min(limit, 200))
        search = request.query_params.get('search')
        plan_type = request.query_params.get('planType')
        subscription_status = request.query_params.get('subscriptionStatus')
        onboarding_status = request.query_params.get('onboardingStatus')
        sort_by = request.query_params.get('sortBy', 'createdAt')
        sort_order = request.query_params.get('sortOrder', 'desc')

        qs = School.objects.all()
        if search:
            qs = qs.filter(name__icontains=search)
        if plan_type:
            qs = qs.filter(Q(subscription__plan__name__iexact=plan_type) | Q(subscription__plan__name__icontains=plan_type))
        if subscription_status:
            qs = qs.filter(Q(subscription__status__iexact=subscription_status) | Q(subscription__status__icontains=subscription_status))
        if onboarding_status:
            school_ids = Onboarding.objects.filter(status__iexact=onboarding_status).values_list('school_id', flat=True)
            qs = qs.filter(id__in=school_ids)

        sort_map = {'createdAt': 'created_at', 'name': 'name'}
        sort_field = sort_map.get(sort_by, 'created_at')
        if sort_order == 'desc':
            sort_field = f'-{sort_field}'
        qs = qs.order_by(sort_field)

        total = qs.count()
        start = page * limit
        schools = qs[start:start+limit]
        serializer = SchoolSerializer(schools, many=True)

        # summary counts
        total_schools = School.objects.count()
        active_subscriptions = Subscription.objects.filter(status='active').count()
        onboarding_in_progress = Onboarding.objects.filter(status='inprogress').count()

        response = {
            'success': True,
            'data': {
                'schools': serializer.data,
                'pagination': {
                    'page': page,
                    'limit': limit,
                    'total': total,
                    'totalPages': (total + limit - 1) // limit if limit else 0
                },
                'summary': {
                    'totalSchools': total_schools,
                    'totalStudents': 0,
                    'activeSubscriptions': active_subscriptions,
                    'onboardingInProgress': onboarding_in_progress
                }
            }
        }
        return Response(response)

    def post(self, request):
        """Create new school - operators/superusers only"""
        if not (request.user.role == 'operator' or request.user.is_superuser):
            return Response({'error': 'Only operators or superusers can create schools'}, status=status.HTTP_403_FORBIDDEN)
        
        serializer = SchoolSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class SchoolDetailsView(APIView):
    """GET: comprehensive school details"""
    permission_classes = [IsAuthenticated]

    def get(self, request, school_id):
        if not (request.user.is_superuser or request.user.role in ['sale_manager', 'sales_assistant', 'operator']):
            return Response({'error': 'Access denied'}, status=status.HTTP_403_FORBIDDEN)
        try:
            school = School.objects.get(id=school_id)
        except School.DoesNotExist:
            return Response({'error': 'School not found'}, status=status.HTTP_404_NOT_FOUND)

        # Get subscription and plan info
        plan_type = 'basic'
        subscription_status = 'inactive'
        if school.subscription:
            plan_type = school.subscription.plan.name.lower() if school.subscription.plan else 'basic'
            subscription_status = school.subscription.status
        
        # Get onboarding info
        onboarding_status = 'not_started'
        onboarding_progress = 0
        completed_steps = {
            'initialSetup': False,
            'staffTraining': False,
            'dataMigration': False,
            'goLive': False
        }
        
        try:
            onboarding = Onboarding.objects.get(school=school)
            onboarding_status = onboarding.status
            onboarding_progress = onboarding.percentage
        except Onboarding.DoesNotExist:
            pass

        # stats
        total_users = school.students.filter(is_active=True).count()
        active_users = total_users  # Assuming all active students are using the system

        data = {
            'success': True,
            'data': {
                'school': {
                    'id': str(school.id),
                    'name': school.name,
                    'planType': plan_type,
                    'subscriptionStatus': subscription_status,
                    'onboardingStatus': onboarding_status,
                    'onboardingProgress': onboarding_progress
                },
                'onboardingSteps': completed_steps,
                'stats': {
                    'totalUsers': total_users,
                    'activeUsers': active_users
                }
            }
        }
        return Response(data)


class SchoolOnboardingUpdateView(APIView):
    """PATCH: Update onboarding progress for a school"""
    permission_classes = [IsAuthenticated]

    def patch(self, request, school_id):
        if not (request.user.is_superuser or request.user.role in ['sale_manager', 'sales_assistant', 'operator']):
            return Response({'error': 'Access denied'}, status=status.HTTP_403_FORBIDDEN)
        try:
            school = School.objects.get(id=school_id)
        except School.DoesNotExist:
            return Response({'error': 'School not found'}, status=status.HTTP_404_NOT_FOUND)

        completed_steps = request.data.get('completedSteps', {})
        
        # Get or create onboarding
        onboarding, created = Onboarding.objects.get_or_create(
            school=school, 
            defaults={
                'onboarding_manager': request.user, 
                'startdate': timezone.now().date(), 
                'expected_go_live_date': timezone.now().date() + timedelta(days=30), 
                'onboarding_type': 'online', 
                'percentage': 0
            }
        )

        # Compute percentage from completed steps
        if completed_steps and isinstance(completed_steps, dict):
            total = len(completed_steps)
            done = sum(1 for v in completed_steps.values() if v)
            onboarding.percentage = int((done / total) * 100) if total else 0
            onboarding.save()

        return Response({
            'success': True, 
            'data': {
                'id': str(school.id),
                'onboardingProgress': onboarding.percentage,
                'completedSteps': completed_steps
            }
        })


class SchoolUpgradeView(APIView):
    """PATCH: Upgrade school plan"""
    permission_classes = [IsAuthenticated]

    def patch(self, request, school_id):
        if not (request.user.is_superuser or request.user.role in ['sale_manager', 'sales_assistant', 'operator']):
            return Response({'error': 'Access denied'}, status=status.HTTP_403_FORBIDDEN)
        new_plan = request.data.get('newPlan')
        effective = request.data.get('effectiveDate')
        if not new_plan:
            return Response({'error': 'newPlan required'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            school = School.objects.get(id=school_id)
        except School.DoesNotExist:
            return Response({'error': 'School not found'}, status=status.HTTP_404_NOT_FOUND)

        plan = Plan.objects.filter(name__iexact=new_plan).first()
        if not plan:
            return Response({'error': 'Plan not found'}, status=status.HTTP_404_NOT_FOUND)

        sub = school.subscription
        if not sub:
            sub = Subscription.objects.create(plan=plan, organisation=school, max_users=plan.max_users or 50, start_credits=plan.total_credits, remaining_credits=plan.total_credits, billing_start_date=timezone.now().date(), billing_end_date=timezone.now().date() + timezone.timedelta(days=30), status='active')
            school.subscription = sub
            school.save()
        else:
            sub.plan = plan
            sub.status = 'active'
            sub.save()

        return Response({'success': True, 'data': {'id': str(school.id), 'name': school.name, 'planType': plan.name, 'subscriptionStatus': sub.status, 'monthlyPrice': float(plan.monthly_price), 'upgradeEffectiveDate': effective or timezone.now().isoformat(), 'updatedAt': sub.updated_at.isoformat()}})


class SchoolSupportHistoryView(APIView):
    """GET: Return support tickets (placeholder)"""
    permission_classes = [IsAuthenticated]

    def get(self, request, school_id):
        if not (request.user.is_superuser or request.user.role in ['sale_manager', 'sales_assistant', 'operator']):
            return Response({'error': 'Access denied'}, status=status.HTTP_403_FORBIDDEN)
        # No support model implemented; return placeholder
        tickets = []
        summary = {'totalTickets': 0, 'openTickets': 0, 'resolvedTickets': 0, 'averageResolutionTime': None}
        return Response({'success': True, 'data': {'tickets': tickets, 'summary': summary}})


class SchoolCancelSubscriptionView(APIView):
    """PATCH: Cancel subscription for a school"""
    permission_classes = [IsAuthenticated]

    def patch(self, request, school_id):
        if not (request.user.is_superuser or request.user.role in ['sale_manager', 'sales_assistant', 'operator']):
            return Response({'error': 'Access denied'}, status=status.HTTP_403_FORBIDDEN)
        reason = request.data.get('reason')
        effective = request.data.get('effectiveDate')
        feedback = request.data.get('feedbackComment')
        try:
            school = School.objects.get(id=school_id)
        except School.DoesNotExist:
            return Response({'error': 'School not found'}, status=status.HTTP_404_NOT_FOUND)

        sub = school.subscription
        if not sub:
            return Response({'error': 'No active subscription found'}, status=status.HTTP_400_BAD_REQUEST)

        sub.status = 'cancelled'
        if effective:
            try:
                sub.billing_end_date = timezone.datetime.fromisoformat(effective).date()
            except Exception:
                pass
        sub.save()

        return Response({'success': True, 'data': {'id': str(school.id), 'subscriptionStatus': sub.status, 'cancellationEffectiveDate': sub.billing_end_date.isoformat() if sub.billing_end_date else None, 'message': 'Subscription will be cancelled on the specified date'}})


class SchoolDetailView(APIView):
    """
    GET: Get school details
    PUT: Update school
    DELETE: Delete school
    """
    permission_classes = [IsSchoolStaffOrAdmin]
    

    def get(self, request, school_id):
        """Get school details"""
        try:
            school = School.objects.get(id=school_id)
            serializer = SchoolSerializer(school)
            return Response(serializer.data)
        except School.DoesNotExist:
            return Response({'error': 'School not found'}, status=status.HTTP_404_NOT_FOUND)

    def put(self, request, school_id):
        """Update school"""
        try:
            school = School.objects.get(id=school_id)
            serializer = SchoolSerializer(school, data=request.data, partial=True)
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        except School.DoesNotExist:
            return Response({'error': 'School not found'}, status=status.HTTP_404_NOT_FOUND)

    def delete(self, request, school_id):
        """Delete school"""
        try:
            school = School.objects.get(id=school_id)
            school.delete()
            return Response({'message': 'School deleted successfully'}, status=status.HTTP_204_NO_CONTENT)
        except School.DoesNotExist:
            return Response({'error': 'School not found'}, status=status.HTTP_404_NOT_FOUND)


# ============================================================================
# STUDENT CRUD VIEWS
# ============================================================================

class StudentListCreateView(APIView):
    """
    GET: List students for a school (school admins/operators)
    POST: Create new student (school admins/operators)
    """
    permission_classes = [IsSchoolStaffOrAdmin]

    def get(self, request, school_id):
        """List students for a school"""
        try:
            school = School.objects.get(id=school_id)
            qs = Student.objects.filter(school=school)

            search = request.query_params.get('search')
            if search:
                qs = qs.filter(
                    Q(first_name__icontains=search) | 
                    Q(last_name__icontains=search) | 
                    Q(school_email__icontains=search) | 
                    Q(student_code__icontains=search)
                )

            qs = qs.order_by('last_name', 'first_name')

            page = int(request.query_params.get('page', 0))
            limit = int(10)
            limit = max(1, min(limit, 200))

            total = qs.count()
            start = page * limit
            students = qs[start:start+limit]

            serializer = StudentSerializer(students, many=True)
            
            return Response({
                'success': True,
                'data': {
                    'students': serializer.data,
                    'pagination': {
                        'page': page,
                        'limit': limit,
                        'total': total,
                        'totalPages': (total + limit - 1) // limit if limit else 0
                    }
                }
            })
        except School.DoesNotExist:
            return Response({'error': 'School not found'}, status=status.HTTP_404_NOT_FOUND)

    def post(self, request, school_id):
        """Create new student"""
        try:
            school = School.objects.get(id=school_id)
        except School.DoesNotExist:
            return Response({'error': 'School not found'}, status=status.HTTP_404_NOT_FOUND)

        # Ensure organisation subscription allows creating one more user
        try:
            ensure_user_slots_available(school, required_slots=1)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_403_FORBIDDEN)

        # Auto-generate student code if not provided
        data = request.data.copy()
        if 'student_code' not in data or not data['student_code']:
            data['student_code'] = self._generate_student_code(school)

        # Ensure school is in data so DRF's PrimaryKeyRelatedField validates it
        data['school'] = str(school.id)
        
        # Pass school via context for create() as well
        serializer = StudentSerializer(
            data=data,
            context={'school': school}
        )
        if serializer.is_valid():
            try:
                serializer.save()
                response_data = serializer.data
                response_data['student_code'] = data.get('student_code')
                return Response(response_data, status=status.HTTP_201_CREATED)
            except IntegrityError as e:
                error_msg = str(e)
                if 'school_id' in error_msg.lower():
                    return Response(
                        {'error': 'School ID is required to create a student'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                elif 'unique_student_code_per_school' in error_msg.lower() or 'student_code' in error_msg.lower():
                    return Response(
                        {'error': f'Student code "{data.get("student_code")}" already exists for this school. Please provide a unique code.'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                else:
                    return Response(
                        {'error': f'Database integrity error: {error_msg}'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
            except Exception as e:
                return Response(
                    {'error': f'An unexpected error occurred while creating the student: {str(e)}'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def _generate_student_code(self, school):
        """Generate unique 5-character student code for school"""
        while True:
            # Generate random 5-character code (letters and numbers)
            code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=5))
            if not Student.objects.filter(school=school, student_code=code).exists():
                return code


class StudentDetailView(APIView):
    """
    GET: Get student details
    PUT: Update student
    DELETE: Delete student
    """
    permission_classes = [IsSchoolStaffOrAdmin]

    def get(self, request, school_id, student_id):
        """Get student details"""
        try:
            student = Student.objects.get(id=student_id, school_id=school_id)
            serializer = StudentSerializer(student)
            return Response(serializer.data)
        except Student.DoesNotExist:
            return Response({'error': 'Student not found'}, status=status.HTTP_404_NOT_FOUND)

    def put(self, request, school_id, student_id):
        """Update student"""
        try:
            student = Student.objects.get(id=student_id, school_id=school_id)
            serializer = StudentSerializer(student, data=request.data, partial=True)
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        except Student.DoesNotExist:
            return Response({'error': 'Student not found'}, status=status.HTTP_404_NOT_FOUND)

    def delete(self, request, school_id, student_id):
        """Delete student"""
        try:
            student = Student.objects.get(id=student_id, school_id=school_id)
            student.delete()
            return Response({'message': 'Student deleted successfully'}, status=status.HTTP_204_NO_CONTENT)
        except Student.DoesNotExist:
            return Response({'error': 'Student not found'}, status=status.HTTP_404_NOT_FOUND)


class StudentBulkCreateView(APIView):
    """
    POST: Bulk create students from Excel file
    Body: multipart/form-data with 'file' field containing Excel file
    Excel format: first_name, last_name, school_email columns
    """
    permission_classes = [IsSchoolStaffOrAdmin]

    def post(self, request, school_id):
        """Bulk create students from Excel"""
        try:
            school = School.objects.get(id=school_id)
        except School.DoesNotExist:
            return Response({'error': 'School not found'}, status=status.HTTP_404_NOT_FOUND)

        if 'file' not in request.FILES:
            return Response({'error': 'No file uploaded'}, status=status.HTTP_400_BAD_REQUEST)

        excel_file = request.FILES['file']

        try:
            # Read Excel file
            df = pd.read_excel(excel_file)

            # Validate required columns
            required_columns = ['first_name', 'last_name']
            if not all(col in df.columns for col in required_columns):
                return Response({
                    'error': f'Excel file must contain columns: {", ".join(required_columns)}'
                }, status=status.HTTP_400_BAD_REQUEST)

            created_students = []
            errors = []

            # Check that the organisation has enough user slots for all rows
            rows_to_create = len(df)
            try:
                ensure_user_slots_available(school, required_slots=rows_to_create)
            except Exception as e:
                return Response({'error': str(e)}, status=status.HTTP_403_FORBIDDEN)

            for index, row in df.iterrows():
                try:
                    # Generate unique student code
                    student_code = self._generate_student_code(school)

                    student_data = {
                        'first_name': str(row['first_name']).strip(),
                        'last_name': str(row['last_name']).strip(),
                        'school_email': school.school_email,
                        'student_code': student_code,
                        'school': school.id
                    }

                    serializer = StudentSerializer(data=student_data)
                    if serializer.is_valid():
                        student = serializer.save()
                        response_data = serializer.data.copy()
                        response_data['student_code'] = student_code
                        created_students.append(response_data)
                    else:
                        errors.append({
                            'row': index + 2,  # +2 because Excel is 1-indexed and header
                            'errors': serializer.errors
                        })

                except Exception as e:
                    errors.append({
                        'row': index + 2,
                        'error': str(e)
                    })

            response_data = {
                'created_count': len(created_students),
                'error_count': len(errors),
                'created_students': created_students,
                'errors': errors
            }

            return Response(response_data, status=status.HTTP_201_CREATED)

        except Exception as e:
            return Response({'error': f'Error processing file: {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)

    def _generate_student_code(self, school):
        """Generate unique 5-character student code for school"""
        while True:
            code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=5))
            if not Student.objects.filter(school=school, student_code=code).exists():
                return code


class StudentCodesView(APIView):
    """
    GET: Display all students and their codes for a school
    """
    permission_classes = [IsSchoolStaffOrAdmin]

    def get(self, request, school_id):
        """Get students with their codes"""
        try:
            school = School.objects.get(id=school_id)
            students = Student.objects.filter(school=school).order_by('last_name', 'first_name')

            student_codes = []
            for student in students:
                student_codes.append({
                    'id': student.id,
                    'first_name': student.first_name,
                    'last_name': student.last_name,
                    'full_name': student.get_full_name(),
                    'school_email': student.school_email,
                    'student_code': student.student_code,
                    'is_active': student.is_active,
                    'created_at': student.created_at.isoformat() if student.created_at else None
                })

            return Response({
                'school': {
                    'id': school.id,
                    'name': school.name,
                    'school_email': school.school_email
                },
                'students': student_codes,
                'total_students': len(student_codes)
            })

        except School.DoesNotExist:
            return Response({'error': 'School not found'}, status=status.HTTP_404_NOT_FOUND)


# ============================================================================
# SCHOOL ACTIVATION/DEACTIVATION VIEWS
# ============================================================================

class SchoolToggleActiveView(APIView):
    """
    PATCH: Toggle school's active status
    """
    permission_classes = [IsSchoolAdminOrOperator]

    def patch(self, request, school_id):
        """Toggle school active/inactive status"""
        try:
            school = School.objects.get(id=school_id)
            school.is_active = not school.is_active
            school.save(update_fields=['is_active'])

            status_text = "activated" if school.is_active else "deactivated"

            return Response({
                'message': f'School {status_text} successfully',
                'school': {
                    'id': school.id,
                    'name': school.name,
                    'is_active': school.is_active
                }
            })

        except School.DoesNotExist:
            return Response({'error': 'School not found'}, status=status.HTTP_404_NOT_FOUND)


# ============================================================================
# STUDENT ACTIVATION/DEACTIVATION VIEWS
# ============================================================================

class StudentToggleActiveView(APIView):
    """
    PATCH: Toggle student's active status
    """
    permission_classes = [IsSchoolAdminOrOperator]

    def patch(self, request, school_id, student_id):
        """Toggle student active/inactive status"""
        try:
            student = Student.objects.get(id=student_id, school_id=school_id)
            student.is_active = not student.is_active
            student.save(update_fields=['is_active'])

            status_text = "activated" if student.is_active else "deactivated"

            return Response({
                'message': f'Student {status_text} successfully',
                'student': {
                    'id': student.id,
                    'first_name': student.first_name,
                    'last_name': student.last_name,
                    'full_name': student.get_full_name(),
                    'school_email': student.school_email,
                    'student_code': student.student_code,
                    'is_active': student.is_active
                }
            })

        except Student.DoesNotExist:
            return Response({'error': 'Student not found'}, status=status.HTTP_404_NOT_FOUND)


class StudentBulkToggleActiveView(APIView):
    """
    PATCH: Bulk toggle active status for multiple students
    Body: {"student_ids": ["uuid1", "uuid2"], "is_active": true/false}
    """
    permission_classes = [IsSchoolAdminOrOperator]

    def patch(self, request, school_id):
        """Bulk toggle student active status"""
        try:
            school = School.objects.get(id=school_id)
        except School.DoesNotExist:
            return Response({'error': 'School not found'}, status=status.HTTP_404_NOT_FOUND)

        student_ids = request.data.get('student_ids', [])
        is_active = request.data.get('is_active')

        if not student_ids:
            return Response({'error': 'student_ids list is required'}, status=status.HTTP_400_BAD_REQUEST)

        if is_active is None:
            return Response({'error': 'is_active boolean is required'}, status=status.HTTP_400_BAD_REQUEST)

        # Update students
        updated_count = Student.objects.filter(
            id__in=student_ids,
            school_id=school_id
        ).update(is_active=is_active)

        status_text = "activated" if is_active else "deactivated"

        return Response({
            'message': f'{updated_count} students {status_text} successfully',
            'updated_count': updated_count,
            'is_active': is_active
        })


# ============================================================================
# SCHOOL ADMIN USER CRUD VIEWS
# ============================================================================

class StaffListCreateView(APIView):
    """
    GET: List staff for a school
    POST: Create new staff
    """
    permission_classes = [IsSchoolStaffOrAdmin]

    def get(self, request, school_id):
        try:
            school = School.objects.get(id=school_id)
            qs = Staff.objects.filter(school=school)

            search = request.query_params.get('search')
            if search:
                qs = qs.filter(
                    Q(first_name__icontains=search) | 
                    Q(last_name__icontains=search) | 
                    Q(school_email__icontains=search)
                )

            qs = qs.order_by('last_name', 'first_name')

            page = int(request.query_params.get('page', 0))
            limit = int(request.query_params.get('limit', 5))
            
            total = qs.count()
            start = page * limit
            staff = qs[start:start+limit]

            serializer = StaffCRUDSerializer(staff, many=True)
            
            return Response({
                'success': True,
                'data': {
                    'staff': serializer.data,
                    'pagination': {
                        'page': page,
                        'limit': limit,
                        'total': total,
                        'totalPages': (total + limit - 1) // limit if limit else 0
                    }
                }
            })
        except School.DoesNotExist:
            return Response({'error': 'School not found'}, status=status.HTTP_404_NOT_FOUND)

    def post(self, request, school_id):
        try:
            school = School.objects.get(id=school_id)
        except School.DoesNotExist:
            return Response({'error': 'School not found'}, status=status.HTTP_404_NOT_FOUND)

        serializer = StaffCRUDSerializer(
            data=request.data,
            context={'school': school}
        )
        if serializer.is_valid():
            try:
                serializer.save()
                return Response(serializer.data, status=status.HTTP_201_CREATED)
            except serializers.ValidationError as e:
                return Response(e.detail, status=status.HTTP_400_BAD_REQUEST)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class StaffDetailView(APIView):
    """
    GET: Get staff details
    PUT: Update staff
    DELETE: Delete staff
    """
    permission_classes = [IsSchoolStaffOrAdmin]

    def get(self, request, school_id, staff_id):
        try:
            staff = Staff.objects.get(id=staff_id, school_id=school_id)
            serializer = StaffCRUDSerializer(staff)
            return Response(serializer.data)
        except Staff.DoesNotExist:
            return Response({'error': 'Staff not found'}, status=status.HTTP_404_NOT_FOUND)

    def put(self, request, school_id, staff_id):
        try:
            staff = Staff.objects.get(id=staff_id, school_id=school_id)
            serializer = StaffCRUDSerializer(staff, data=request.data, partial=True)
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        except Staff.DoesNotExist:
            return Response({'error': 'Staff not found'}, status=status.HTTP_404_NOT_FOUND)

    def delete(self, request, school_id, staff_id):
        try:
            staff = Staff.objects.get(id=staff_id, school_id=school_id)
            staff.delete()
            return Response({'message': 'Staff deleted successfully'}, status=status.HTTP_204_NO_CONTENT)
        except Staff.DoesNotExist:
            return Response({'error': 'Staff not found'}, status=status.HTTP_404_NOT_FOUND)


# ============================================================================
# ACTIVITY ENDPOINTS
# ============================================================================

class ActivityListCreateView(APIView):
    """List and create activities"""
    permission_classes = [IsSchoolStaffOrAdmin]

    def get(self, request, school_id):
        try:
            school = School.objects.get(id=school_id)
            qs = Activity.objects.filter(school=school)

            search = request.query_params.get('search')
            if search:
                qs = qs.filter(
                    Q(user_name__icontains=search) | 
                    Q(action__icontains=search) | 
                    Q(tool__icontains=search)
                )

            # Keep ordering from model
            page = int(request.query_params.get('page', 0))
            limit = int(request.query_params.get('limit', 5))  # PAGE_SIZE = 5 default
            
            total = qs.count()
            start = page * limit
            activities = qs[start:start+limit]

            serializer = ActivitySerializer(activities, many=True)
            
            return Response({
                'success': True,
                'data': {
                    'activities': serializer.data,
                    'pagination': {
                        'page': page,
                        'limit': limit,
                        'total': total,
                        'totalPages': (total + limit - 1) // limit if limit else 0
                    }
                }
            })
        except School.DoesNotExist:
            return Response({'error': 'School not found'}, status=status.HTTP_404_NOT_FOUND)

    def post(self, request, school_id):
        try:
            school = School.objects.get(id=school_id)
        except School.DoesNotExist:
            return Response({'error': 'School not found'}, status=status.HTTP_404_NOT_FOUND)

        serializer = ActivitySerializer(
            data=request.data,
            context={'school': school}
        )
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ActivityDetailView(APIView):
    """Update and delete activities"""
    permission_classes = [IsSchoolStaffOrAdmin]

    def get(self, request, school_id, activity_id):
        try:
            activity = Activity.objects.get(id=activity_id, school_id=school_id)
            serializer = ActivitySerializer(activity)
            return Response(serializer.data)
        except Activity.DoesNotExist:
            return Response({'error': 'Activity not found'}, status=status.HTTP_404_NOT_FOUND)

    def put(self, request, school_id, activity_id):
        try:
            activity = Activity.objects.get(id=activity_id, school_id=school_id)
            serializer = ActivitySerializer(activity, data=request.data, partial=True)
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        except Activity.DoesNotExist:
            return Response({'error': 'Activity not found'}, status=status.HTTP_404_NOT_FOUND)

    def delete(self, request, school_id, activity_id):
        try:
            activity = Activity.objects.get(id=activity_id, school_id=school_id)
            activity.delete()
            return Response({'message': 'Activity deleted successfully'}, status=status.HTTP_204_NO_CONTENT)
        except Activity.DoesNotExist:
            return Response({'error': 'Activity not found'}, status=status.HTTP_404_NOT_FOUND)


# ============================================================================

class SchoolAdminUserListCreateView(APIView):
    """
    GET: List all school admin users (operators/superusers only)
    POST: Create new school admin user (operators/superusers only)
    """
    permission_classes = [IsOwnerLevel]

    def get(self, request):
        """List all school admin users"""
        from django.contrib.auth import get_user_model
        User = get_user_model()
        
        # Get all users with role 'school_admin'
        admin_users = User.objects.filter(role='school_admin').select_related('managed_school')
        
        # Serialize the data
        data = []
        for user in admin_users:
            school_info = None
            if hasattr(user, 'managed_school') and user.managed_school:
                school_info = {
                    'id': user.managed_school.id,
                    'name': user.managed_school.name,
                    'school_email': user.managed_school.school_email,
                    'is_active': user.managed_school.is_active
                }
            
            data.append({
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'first_name': user.first_name,
                'last_name': user.last_name,
                'is_active': user.is_active,
                'is_verified': user.is_verified,
                'created_at': user.created_at,
                'school': school_info
            })
        
        return Response({
            'school_admin_users': data,
            'count': len(data)
        })

    def post(self, request):
        """Create new school admin user"""
        from django.contrib.auth import get_user_model
        from django.contrib.auth.password_validation import validate_password
        from django.core.exceptions import ValidationError
        
        User = get_user_model()
        
        # Required fields
        email = request.data.get('email')
        password = request.data.get('password')
        username = request.data.get('username', email)  # Default username to email
        first_name = request.data.get('first_name', '')
        last_name = request.data.get('last_name', '')
        
        if not email or not password:
            return Response({
                'error': 'Email and password are required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Validate password
        try:
            validate_password(password)
        except ValidationError as e:
            return Response({
                'error': 'Password validation failed',
                'details': e.messages
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Check if user already exists
        if User.objects.filter(email=email).exists():
            return Response({
                'error': 'User with this email already exists'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        if User.objects.filter(username=username).exists():
            return Response({
                'error': 'User with this username already exists'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Create the user
        try:
            user = User.objects.create_user(
                username=username,
                email=email,
                password=password,
                first_name=first_name,
                last_name=last_name,
                role='school_admin'
            )
            
            return Response({
                'message': 'School admin user created successfully',
                'user': {
                    'id': user.id,
                    'username': user.username,
                    'email': user.email,
                    'first_name': user.first_name,
                    'last_name': user.last_name,
                    'role': user.role,
                    'is_active': user.is_active,
                    'created_at': user.created_at
                }
            }, status=status.HTTP_201_CREATED)
            
        except Exception as e:
            return Response({
                'error': f'Failed to create user: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class SchoolAdminUserDetailView(APIView):
    """
    GET: Get school admin user details
    PUT: Update school admin user
    DELETE: Delete school admin user
    """
    permission_classes = [IsOwnerLevel]

    def get(self, request, user_id):
        """Get school admin user details"""
        from django.contrib.auth import get_user_model
        User = get_user_model()
        
        try:
            user = User.objects.select_related('managed_school').get(id=user_id, role='school_admin')
        except User.DoesNotExist:
            return Response({
                'error': 'School admin user not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        school_info = None
        if hasattr(user, 'managed_school') and user.managed_school:
            school_info = {
                'id': user.managed_school.id,
                'name': user.managed_school.name,
                'school_email': user.managed_school.school_email,
                'is_active': user.managed_school.is_active
            }
        
        return Response({
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'is_active': user.is_active,
            'is_verified': user.is_verified,
            'created_at': user.created_at,
            'updated_at': user.updated_at,
            'school': school_info
        })

    def put(self, request, user_id):
        """Update school admin user"""
        from django.contrib.auth import get_user_model
        User = get_user_model()
        
        try:
            user = User.objects.get(id=user_id, role='school_admin')
        except User.DoesNotExist:
            return Response({
                'error': 'School admin user not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Fields that can be updated
        updatable_fields = [
            'first_name', 'last_name', 'is_active', 'is_verified'
        ]
        
        updated = False
        for field in updatable_fields:
            if field in request.data:
                setattr(user, field, request.data[field])
                updated = True
        
        if updated:
            user.save()
            return Response({
                'message': 'School admin user updated successfully',
                'user': {
                    'id': user.id,
                    'username': user.username,
                    'email': user.email,
                    'first_name': user.first_name,
                    'last_name': user.last_name,
                    'is_active': user.is_active,
                    'is_verified': user.is_verified
                }
            })
        else:
            return Response({
                'message': 'No changes made'
            })

    def delete(self, request, user_id):
        """Delete school admin user"""
        from django.contrib.auth import get_user_model
        User = get_user_model()
        
        try:
            user = User.objects.get(id=user_id, role='school_admin')
        except User.DoesNotExist:
            return Response({
                'error': 'School admin user not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Check if user is linked to a school
        if hasattr(user, 'managed_school') and user.managed_school:
            return Response({
                'error': 'Cannot delete school admin user that is linked to a school. Delete the school first.'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        user.delete()
        return Response({
            'message': 'School admin user deleted successfully'
        })



class InviteStaffView(APIView):
    """Create an invitation for a staff member to join a school.

    School admins or operators can create invitations. The invitation
    contains a `code` that is sent to the staff email (frontend will build
    the URL like `https://frontendurl?code=...`).
    """
    permission_classes = [IsSchoolAdminOrOperator]

    def post(self, request, school_id):
        try:
            school = School.objects.get(id=school_id)
        except School.DoesNotExist:
            return Response({'error': 'School not found'}, status=status.HTTP_404_NOT_FOUND)

        serializer = InvitationSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        email = data['email']
        role = data.get('role', 'teacher')

        # generate a secure random code
        code = _uuid.uuid4().hex

        # Check that the school can accept another user slot before creating invite
        try:
            ensure_user_slots_available(school, required_slots=1)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_403_FORBIDDEN)

        invite = Invitation.objects.create(
            email=email,
            school=school,
            role=role,
            code=code,
            invited_by=request.user,
            expires_at=timezone.now() + timezone.timedelta(days=7)
        )

        # Build frontend link: FRONTEND_URL?code=<code>
        frontend_base = getattr(settings, 'FRONTEND_URL', '').rstrip('/')
        invite_link = f"{frontend_base}/invite/accept/?code={invite.code}"

        # Render email templates
        context = {
            'invite_link': invite_link,
            'school': school,
            'role_display': invite.get_role_display(),
            'inviter': request.user,
        }

        subject = f"You're invited to join {school.name}"
        try:
            text_body = render_to_string('schools/invitation_email.txt', context)
        except Exception:
            text_body = f"You have been invited to join {school.name}. Visit {invite_link} to accept."

        try:
            html_body = render_to_string('schools/invitation_email.html', context)
        except Exception:
            html_body = f"<p>You have been invited to join <strong>{school.name}</strong>. <a href=\"{invite_link}\">Accept invite</a></p>"

        from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', None)

        try:
            msg = EmailMultiAlternatives(subject, text_body, from_email, [invite.email])
            msg.attach_alternative(html_body, "text/html")
            msg.send()
        except Exception:
            return Response({'message': 'Invitation created', 'code': invite.code, 'warning': 'Failed to send email'}, status=status.HTTP_201_CREATED)

        return Response({'message': 'Invitation created and email sent', 'code': invite.code}, status=status.HTTP_201_CREATED)


class AcceptInvitationView(APIView):
    """Accept an invitation using a code and create a linked User+Staff.

    Frontend will call this endpoint with the `code` (from URL) and user
    supplied `password`, `confirm_password`, `first_name`, and optionally
    `school_id` and `role` (second modal). The server validates the
    invitation and creates the account, linking it to the school.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        # Accept code from body or query params (frontend may send code in URL)
        data = request.data.copy() if hasattr(request, 'data') else {}
        if not data.get('code'):
            qp = request.query_params.get('code') if hasattr(request, 'query_params') else None
            if qp:
                data['code'] = qp

        serializer = AcceptInvitationSerializer(data=data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        code = data['code']

        try:
            invite = Invitation.objects.get(code=code)
        except Invitation.DoesNotExist:
            return Response({'error': 'Invalid invitation code'}, status=status.HTTP_400_BAD_REQUEST)

        if not invite.is_valid():
            return Response({'error': 'Invitation expired or already used'}, status=status.HTTP_400_BAD_REQUEST)

        # Ensure organisation subscription is active
        if not is_subscription_active_for_user_or_org(request.user if request.user.is_authenticated else None):
            # If the acceptor is anonymous, check organisation subscription via invite
            org_sub_active = is_subscription_active_for_user_or_org(invite.invited_by) if invite.invited_by else False
            if not org_sub_active:
                return Response({'error': 'Organisation subscription inactive'}, status=status.HTTP_403_FORBIDDEN)

        # Ensure there's still a user slot available before creating the account
        try:
            ensure_user_slots_available(invite.school, required_slots=1)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_403_FORBIDDEN)

        # If frontend supplied school_id or role, validate they match
        if data.get('school_id') and str(invite.school.id) != str(data.get('school_id')):
            return Response({'error': 'School does not match invitation'}, status=status.HTTP_400_BAD_REQUEST)

        if data.get('role') and data.get('role') != invite.role:
            return Response({'error': 'Role does not match invitation'}, status=status.HTTP_400_BAD_REQUEST)

        password = data['password']
        first_name = data.get('first_name', '')
        last_name = data.get('last_name', '')

        User = get_user_model()

        # Validate password using Django validators
        try:
            validate_password(password)
        except ValidationError as e:
            return Response({'error': 'Password validation failed', 'details': e.messages}, status=status.HTTP_400_BAD_REQUEST)

        # Ensure user doesn't already exist
        if User.objects.filter(email=invite.email).exists():
            return Response({'error': 'User with this email already exists'}, status=status.HTTP_400_BAD_REQUEST)

        # Create the user
        user = User.objects.create_user(
            username=invite.email,
            email=invite.email,
            password=password,
            first_name=first_name,
            last_name=last_name,
            user_type='enterprise',
            organisation=invite.school,
            role=invite.role
        )

        # Create Staff record
        Staff.objects.create(
            school=invite.school,
            first_name=first_name,
            last_name=last_name,
            school_email=invite.email,
            role=invite.role
        )

        # Mark invitation used
        invite.used = True
        invite.save(update_fields=['used'])

        return Response({'message': 'Account created', 'user_id': user.id}, status=status.HTTP_201_CREATED)


# ============================================================================
# ADMIN DASHBOARD VIEWS
# ============================================================================

class AdminDashboardView(APIView):
    """
    GET: Get admin dashboard data
    """
    permission_classes = [IsOwnerLevel]

    def get(self, request):
        """Get comprehensive admin dashboard data"""
        today = timezone.now().date()
        yesterday = today - timedelta(days=1)
        current_month = today.replace(day=1)
        last_month = (current_month - timedelta(days=1)).replace(day=1)

        # Total schools with percentage change
        total_schools = School.objects.count()
        yesterday_schools = School.objects.filter(created_at__date__lte=yesterday).count()
        schools_change = self._calculate_percentage_change(total_schools, yesterday_schools)

        # Active schools
        active_schools = School.objects.filter(is_active=True).count()
        active_schools_percentage = (active_schools / total_schools * 100) if total_schools > 0 else 0

        # Total users and current month users
        User = get_user_model()
        total_users = User.objects.count()
        current_month_users = User.objects.filter(created_at__date__gte=current_month).count()

        # AI requests with percentage change
        total_ai_requests = AILog.objects.count()
        yesterday_ai_requests = AILog.objects.filter(created_at__date__lte=yesterday).count()
        ai_requests_change = self._calculate_percentage_change(total_ai_requests, yesterday_ai_requests)

        # Total tokens used today
        today_tokens = AILog.objects.filter(created_at__date=today).aggregate(
            total_tokens=Sum('total_tokens')
        )['total_tokens'] or 0

        # Monthly cost with percentage change
        current_month_cost = AILog.objects.filter(
            created_at__date__gte=current_month
        ).aggregate(total_cost=Sum('cost'))['total_cost'] or 0

        last_month_cost = AILog.objects.filter(
            created_at__date__gte=last_month,
            created_at__date__lt=current_month
        ).aggregate(total_cost=Sum('cost'))['total_cost'] or 0

        monthly_cost_change = self._calculate_percentage_change(current_month_cost, last_month_cost)

        # Graph data: usage over months (last 12 months)
        usage_graph_data = self._get_usage_over_months()

        # Graph data: cost over months (last 12 months)
        cost_graph_data = self._get_cost_over_months()

        # Donut chart: tools usage distribution
        tools_distribution = self._get_tools_distribution()

        # Top 5 schools by AI usage
        top_schools = self._get_top_schools_by_ai_usage()

        # Recent 5 AI activities
        recent_activities = self._get_recent_ai_activities()

        # Additional admin metrics requested: students, staff, active users, credit usage
        total_students = Student.objects.count()
        total_staff = Staff.objects.count()
        total_active_users = User.objects.filter(is_active=True).count()

        # Credit usage percentage across subscriptions (remaining / start * 100)
        totals = Subscription.objects.aggregate(
            total_start=Sum('start_credits'),
            total_remaining=Sum('remaining_credits')
        )
        total_start = totals.get('total_start') or 0
        total_remaining = totals.get('total_remaining') or 0
        credit_remaining_percentage = (total_remaining / total_start * 100) if total_start > 0 else 0

        # Credit over months graph
        credit_graph_data = self._get_credit_over_months()

        return Response({
            'summary': {
                'total_schools': total_schools,
                'schools_change_percentage': schools_change,
                'active_schools': active_schools,
                'active_schools_percentage': round(active_schools_percentage, 2),
                'total_users': total_users,
                'current_month_users': current_month_users,
                'total_ai_requests': total_ai_requests,
                'ai_requests_change_percentage': ai_requests_change,
                'today_tokens': today_tokens,
                'monthly_cost': float(current_month_cost),
                'monthly_cost_change_percentage': monthly_cost_change,
            },
            'graphs': {
                'usage_over_months': usage_graph_data,
                'cost_over_months': cost_graph_data,
                'credit_over_months': credit_graph_data,
            },
            'charts': {
                'tools_distribution': tools_distribution,
            },
            'top_schools': top_schools,
            'recent_activities': recent_activities,
            'additional': {
                'total_students': total_students,
                'total_staff': total_staff,
                'total_active_users': total_active_users,
                'total_start_credits': int(total_start) if total_start is not None else 0,
                'total_remaining_credits': int(total_remaining) if total_remaining is not None else 0,
                'credit_remaining_percentage': round(credit_remaining_percentage, 2)
            }
        })

    def _calculate_percentage_change(self, current, previous):
        """Calculate percentage change between current and previous values"""
        if previous == 0:
            return 100.0 if current > 0 else 0.0
        return round(((current - previous) / previous) * 100, 2)

    def _get_usage_over_months(self):
        """Get AI usage data over the last 12 months"""
        end_date = timezone.now().date()
        start_date = end_date - timedelta(days=365)

        usage_data = AILog.objects.filter(
            created_at__date__gte=start_date
        ).annotate(
            month=TruncMonth('created_at')
        ).values('month').annotate(
            total_requests=Count('id'),
            total_tokens=Sum('total_tokens')
        ).order_by('month')

        return list(usage_data)

    def _get_cost_over_months(self):
        """Get cost data over the last 12 months"""
        end_date = timezone.now().date()
        start_date = end_date - timedelta(days=365)

        cost_data = AILog.objects.filter(
            created_at__date__gte=start_date
        ).annotate(
            month=TruncMonth('created_at')
        ).values('month').annotate(
            total_cost=Sum('cost')
        ).order_by('month')

        return list(cost_data)

    def _get_tools_distribution(self):
        """Get tools usage distribution for donut chart"""
        tool_usage = AILog.objects.values('tool').annotate(
            usage_count=Count('id'),
            total_tokens=Sum('total_tokens')
        ).order_by('-usage_count')

        total_usage = sum(item['usage_count'] for item in tool_usage)

        distribution = []
        for item in tool_usage:
            percentage = (item['usage_count'] / total_usage * 100) if total_usage > 0 else 0
            distribution.append({
                'tool': item['tool'],
                'usage_count': item['usage_count'],
                'total_tokens': item['total_tokens'],
                'percentage': round(percentage, 2)
            })

        return distribution

    def _get_top_schools_by_ai_usage(self):
        """Get top 5 schools by AI usage"""
        # Get schools with their AI usage
        school_usage = AILog.objects.values('user__organisation').annotate(
            ai_usage=Count('id'),
            total_tokens=Sum('total_tokens')
        ).filter(
            user__organisation__isnull=False
        ).order_by('-ai_usage')[:5]

        top_schools = []
        for usage in school_usage:
            school_id = usage['user__organisation']
            school = School.objects.get(id=school_id)

            # Get subscription info
            subscription = Subscription.objects.filter(
                organisation=school,
                status='active'
            ).first()

            plan_info = None
            max_users = 0
            if subscription:
                plan_info = subscription.plan.name
                max_users = subscription.max_users

            # Count current users
            current_users = school.users.count()

            top_schools.append({
                'school_name': school.name,
                'plan': plan_info,
                'users': current_users,
                'limit_users_per_subscription': max_users,
                'ai_usage': usage['ai_usage'],
                'status': 'active' if school.is_active else 'inactive'
            })

        return top_schools

    def _get_recent_ai_activities(self):
        """Get recent 5 AI activities"""
        recent_logs = AILog.objects.select_related('user').order_by('-created_at')[:5]

        activities = []
        for log in recent_logs:
            # Calculate time ago in minutes
            time_diff = timezone.now() - log.created_at
            minutes_ago = int(time_diff.total_seconds() / 60)

            activities.append({
                'time_minutes_ago': minutes_ago,
                'username': log.user.username,
                'tools': log.tool,
                'tokens': log.total_tokens,
                'status': 'success'  # Assuming all logged activities are successful
            })

        return activities

    def _get_credit_over_months(self):
        """Get credit additions (tops) over the last 12 months"""
        end_date = timezone.now().date()
        start_date = end_date - timedelta(days=365)

        credit_data = CreditTop.objects.filter(
            purchase_date__gte=start_date
        ).annotate(
            month=TruncMonth('purchase_date')
        ).values('month').annotate(
            total_credits=Sum('credit_add')
        ).order_by('month')

        # Ensure months with zero are represented could be handled client-side
        return list(credit_data)


class SchoolAdminDashboardView(APIView):
    """
    GET: Dashboard scoped to a school for school admins (or operators viewing a specific school)
    """
    permission_classes = [IsSchoolAdminOrOperator]

    def get(self, request, school_id=None):
        """Return school-scoped metrics: students, staff, credit usage, active users, recent activities, credit graph"""
        # Resolve school: for school_admin use their managed_school, operators may pass school_id
        user = request.user
        school = None
        if getattr(user, 'is_authenticated', False) and getattr(user, 'role', None) == 'school_admin':
            school = getattr(user, 'managed_school', None)
            if not school:
                return Response({'error': 'No school linked to this admin'}, status=status.HTTP_404_NOT_FOUND)
        else:
            if not school_id:
                return Response({'error': 'school_id is required'}, status=status.HTTP_400_BAD_REQUEST)
            try:
                school = School.objects.get(id=school_id)
            except School.DoesNotExist:
                return Response({'error': 'School not found'}, status=status.HTTP_404_NOT_FOUND)

        # Counts
        total_students = Student.objects.filter(school=school).count()
        total_staff = Staff.objects.filter(school=school).count()
        User = get_user_model()
        total_active_users = User.objects.filter(organisation=school, is_active=True).count()

        # Credit usage for this school (aggregate subscriptions belonging to organisation)
        totals = Subscription.objects.filter(organisation=school).aggregate(
            total_start=Sum('start_credits'),
            total_remaining=Sum('remaining_credits')
        )
        total_start = totals.get('total_start') or 0
        total_remaining = totals.get('total_remaining') or 0
        credit_remaining_percentage = (total_remaining / total_start * 100) if total_start > 0 else 0

        # Recent activities (most recent 5) scoped to this school's users
        recent_logs = AILog.objects.filter(user__organisation=school).select_related('user').order_by('-created_at')[:5]
        recent_activities = []
        for log in recent_logs:
            u = log.user
            full_name = u.get_full_name() if hasattr(u, 'get_full_name') and callable(u.get_full_name) else (u.username or '')
            title = log.topic if log.topic else (log.prompt[:120] if log.prompt else '')
            recent_activities.append({
                'name': full_name,
                'role': getattr(u, 'role', None),
                'time': log.created_at.isoformat(),
                'title': title,
                'tool': log.tool
            })

        # Credit over months for this organisation (last 12 months)
        end_date = timezone.now().date()
        start_date = end_date - timedelta(days=365)
        credit_graph = CreditTop.objects.filter(
            organisation=school,
            purchase_date__gte=start_date
        ).annotate(
            month=TruncMonth('purchase_date')
        ).values('month').annotate(
            total_credits=Sum('credit_add')
        ).order_by('month')

        return Response({
            'school': {
                'id': school.id,
                'name': school.name,
            },
            'summary': {
                'total_students': total_students,
                'total_staff': total_staff,
                'total_active_users': total_active_users,
                'total_start_credits': int(total_start) if total_start is not None else 0,
                'total_remaining_credits': int(total_remaining) if total_remaining is not None else 0,
                'credit_remaining_percentage': round(credit_remaining_percentage, 2)
            },
            'recent_activities': recent_activities,
            'graphs': {
                'credit_over_months': list(credit_graph)
            }
        })

    # The helper methods above are also used by the AdminDashboardView; the
    # duplicates that were previously placed after SchoolAdminDashboardView
    # have been removed to avoid method shadowing and AttributeError.

class SchoolMonitoringView(APIView):
    """
    GET: Get detailed monitoring and alerts for a specific school (Superusers/Operators only)
    """
    permission_classes = [IsOwnerLevel]

    def get(self, request, school_id):
        try:
            school = School.objects.get(id=school_id)
        except School.DoesNotExist:
            return Response({'error': 'School not found'}, status=status.HTTP_404_NOT_FOUND)

        # 1. Subscription & Billing
        billing = {
            'status': 'no_subscription',
            'plan': None,
            'start_credits': 0,
            'remaining_credits': 0,
            'billing_start_date': None,
            'billing_end_date': None,
            'monthly_price': 0,
            'percentage_used': 0,
        }
        
        subscription = Subscription.objects.filter(organisation=school, status='active').first()
        if subscription:
            billing['status'] = subscription.status
            billing['plan'] = subscription.plan.name if subscription.plan else None
            billing['start_credits'] = subscription.start_credits
            billing['remaining_credits'] = subscription.remaining_credits
            billing['billing_start_date'] = subscription.billing_start_date.isoformat() if subscription.billing_start_date else None
            billing['billing_end_date'] = subscription.billing_end_date.isoformat() if subscription.billing_end_date else None
            if subscription.plan:
                billing['monthly_price'] = float(subscription.plan.monthly_price)
            if subscription.start_credits > 0:
                used = subscription.start_credits - subscription.remaining_credits
                billing['percentage_used'] = round((used / subscription.start_credits) * 100, 2)

        # 2. Usage & AI Monitoring (Last 30 days)
        end_date = timezone.now().date()
        start_date = end_date - timedelta(days=30)
        
        usage_data = AILog.objects.filter(
            user__organisation=school,
            created_at__date__gte=start_date
        ).annotate(
            day=TruncDay('created_at')
        ).values('day').annotate(
            total_requests=Count('id'),
            total_tokens=Sum('total_tokens')
        ).order_by('day')
        
        usage_over_time = []
        for d in usage_data:
            usage_over_time.append({
                'date': d['day'].date().isoformat() if hasattr(d['day'], 'date') else d['day'].isoformat(),
                'requests': d['total_requests'],
                'tokens': d['total_tokens']
            })

        # 3. Alerts & Risk Monitoring
        alerts = []
        
        # Alert 1: Student limit exceeded
        active_students = school.students.filter(is_active=True).count()
        if active_students > school.max_students:
            alerts.append({
                'type': 'student_limit_exceeded',
                'severity': 'high',
                'message': f'School has {active_students} active students, exceeding limit of {school.max_students}.'
            })
            
        # Alert 2: Subscription expired
        expired_sub = Subscription.objects.filter(organisation=school, status='expired').first()
        if expired_sub and not subscription:
            alerts.append({
                'type': 'subscription_expired',
                'severity': 'high',
                'message': f'The subscription for plan {expired_sub.plan.name if expired_sub.plan else "Unknown"} has expired.'
            })
            
        # Alert 3: Unusual usage spike
        today_usage = sum([u['tokens'] for u in usage_over_time if u['date'] == end_date.isoformat()])
        week_ago = end_date - timedelta(days=7)
        past_week_usage = [u['tokens'] for u in usage_over_time if u['date'] >= week_ago.isoformat() and u['date'] < end_date.isoformat()]
        
        avg_week_usage = sum(past_week_usage) / len(past_week_usage) if past_week_usage else 0
        
        if today_usage > 1000 and today_usage > (avg_week_usage * 2):
            alerts.append({
                'type': 'unusual_usage_spike',
                'severity': 'medium',
                'message': f'Unusual usage detected: {today_usage} tokens today (average is {int(avg_week_usage)}/day).'
            })

        return Response({
            'success': True,
            'data': {
                'school': {
                    'id': str(school.id),
                    'name': school.name,
                    'is_active': school.is_active,
                    'active_students': active_students,
                    'max_students': school.max_students
                },
                'billing': billing,
                'monitoring': {
                    'usage_last_30_days': usage_over_time
                },
                'alerts': alerts
            }
        })


class GlobalAlertsView(APIView):
    """
    GET: Get all active alerts across all schools (Superusers/Operators only)
    """
    permission_classes = [IsOwnerLevel]

    def get(self, request):
        active_schools = School.objects.filter(is_active=True)
        end_date = timezone.now().date()
        start_date = end_date - timedelta(days=7)
        
        all_alerts = []
        
        for school in active_schools:
            school_alerts = []
            
            # 1. Student Limit
            active_students = school.students.filter(is_active=True).count()
            if active_students > school.max_students:
                school_alerts.append({
                    'type': 'student_limit_exceeded',
                    'severity': 'high',
                    'message': f'School has {active_students} active students, exceeding limit of {school.max_students}.'
                })
                
            # 2. Subscription
            active_sub = Subscription.objects.filter(organisation=school, status='active').exists()
            if not active_sub:
                expired_sub = Subscription.objects.filter(organisation=school, status='expired').exists()
                if expired_sub:
                    school_alerts.append({
                        'type': 'subscription_expired',
                        'severity': 'high',
                        'message': 'The subscription has expired.'
                    })
                    
            # 3. Usage Spike
            usage_data = AILog.objects.filter(
                user__organisation=school,
                created_at__date__gte=start_date
            ).annotate(
                day=TruncDay('created_at')
            ).values('day').annotate(
                total_tokens=Sum('total_tokens')
            )
            
            usage_by_day = {d['day'].date().isoformat() if hasattr(d['day'], 'date') else d['day'].isoformat(): d['total_tokens'] for d in usage_data}
            today_str = end_date.isoformat()
            today_tokens = usage_by_day.get(today_str, 0)
            
            past_week_tokens = [tokens for day_str, tokens in usage_by_day.items() if day_str != today_str]
            avg_week_tokens = sum(past_week_tokens) / len(past_week_tokens) if past_week_tokens else 0
            
            if today_tokens > 1000 and today_tokens > (avg_week_tokens * 2):
                school_alerts.append({
                    'type': 'unusual_usage_spike',
                    'severity': 'medium',
                    'message': f'Unusual usage detected: {today_tokens} tokens today (average is {int(avg_week_tokens)}/day).'
                })
                
            if school_alerts:
                all_alerts.append({
                    'school_id': str(school.id),
                    'school_name': school.name,
                    'alerts': school_alerts
                })

        return Response({
            'success': True,
            'data': all_alerts,
            'summary': {
                'total_schools_with_alerts': len(all_alerts),
                'total_alerts': sum(len(sa['alerts']) for sa in all_alerts)
            }
        })

class SchoolNotificationsView(APIView):
    """
    GET: Get alerts/notifications for a specific school (SchoolAdmin / Operators)
    """
    permission_classes = [IsSchoolAdminOrOperator]

    def get(self, request, school_id=None):
        # Resolve school
        user = request.user
        school = None
        if getattr(user, 'is_authenticated', False) and getattr(user, 'role', None) == 'school_admin':
            school = getattr(user, 'managed_school', None)
        elif school_id:
            try:
                school = School.objects.get(id=school_id)
            except School.DoesNotExist:
                return Response({'error': 'School not found'}, status=status.HTTP_404_NOT_FOUND)
        
        if not school:
            return Response({'error': 'No school linked'}, status=status.HTTP_404_NOT_FOUND)

        alerts = []
        
        # 1. Student Limit
        active_students = school.students.filter(is_active=True).count()
        if active_students > school.max_students:
            alerts.append({
                'id': 'alert-student-limit',
                'title': 'Student Limit Exceeded',
                'description': f'You have {active_students} active students, exceeding your plan limit of {school.max_students}.',
                'time': timezone.now().isoformat(),
                'type': 'warning',
                'icon': 'ShieldAlert',
                'isRead': False
            })

        # 2. Subscription Expiry / Renewals
        subscription = Subscription.objects.filter(organisation=school, status='active').first()
        if not subscription:
            alerts.append({
                'id': 'alert-sub-expired',
                'title': 'Subscription Inactive or Expired',
                'description': 'Your school currently has no active subscription. Please top up or upgrade your plan.',
                'time': timezone.now().isoformat(),
                'type': 'critical',
                'icon': 'CreditCard',
                'isRead': False
            })
        elif subscription.billing_end_date:
            days_left = (subscription.billing_end_date - timezone.now().date()).days
            if days_left <= 7 and days_left > 0:
                alerts.append({
                    'id': 'alert-sub-expiring',
                    'title': 'Subscription Ending Soon',
                    'description': f'Your subscription expires in {days_left} days. Please renew to avoid interruption.',
                    'time': timezone.now().isoformat(),
                    'type': 'warning',
                    'icon': 'Clock',
                    'isRead': False
                })

        # 3. Credits nearly exhausted
        if subscription and subscription.start_credits > 0:
            if subscription.remaining_credits < (0.1 * subscription.start_credits):
                alerts.append({
                    'id': 'alert-credits-low',
                    'title': 'Low AI Credits',
                    'description': f'You have used over 90% of your AI credits ({subscription.remaining_credits} credits remaining).',
                    'time': timezone.now().isoformat(),
                    'type': 'warning',
                    'icon': 'Zap',
                    'isRead': False
                })

        return Response({
            'success': True,
            'data': alerts
        })


class SchoolBillingView(APIView):
    """
    GET: Get billing status, limits, and credit history (mock invoices) for a school
    """
    permission_classes = [IsSchoolAdminOrOperator]

    def get(self, request, school_id=None):
        user = request.user
        school = None
        if getattr(user, 'is_authenticated', False) and getattr(user, 'role', None) == 'school_admin':
            school = getattr(user, 'managed_school', None)
        elif school_id:
            try:
                school = School.objects.get(id=school_id)
            except School.DoesNotExist:
                return Response({'error': 'School not found'}, status=status.HTTP_404_NOT_FOUND)
        
        if not school:
            return Response({'error': 'No school linked'}, status=status.HTTP_404_NOT_FOUND)

        subscription = Subscription.objects.filter(organisation=school, status='active').first()
        
        billing_data = {
            'status': 'no_subscription',
            'plan': 'None',
            'start_credits': 0,
            'remaining_credits': 0,
            'percentage_used': 0,
            'billing_end_date': None,
            'max_users': 0,
            'active_students': school.students.filter(is_active=True).count(),
            'active_teachers': Staff.objects.filter(school=school).count()
        }

        if subscription:
            billing_data['status'] = subscription.status
            billing_data['plan'] = subscription.plan.name if subscription.plan else 'Custom Plan'
            billing_data['start_credits'] = subscription.start_credits
            billing_data['remaining_credits'] = subscription.remaining_credits
            billing_data['max_users'] = subscription.max_users
            if subscription.billing_end_date:
                billing_data['billing_end_date'] = subscription.billing_end_date.isoformat()
            
            if subscription.start_credits > 0:
                used = subscription.start_credits - subscription.remaining_credits
                billing_data['percentage_used'] = round((used / subscription.start_credits) * 100, 2)

        # Invoices (Fetch from CreditTop history to mock invoice creation)
        tops = CreditTop.objects.filter(organisation=school).order_by('-purchase_date')
        invoices = []
        for i, top in enumerate(tops):
            invoices.append({
                'id': f'INV-{str(top.id).zfill(4)}',
                'date': top.purchase_date.strftime('%b %d, %Y'),
                'amount': f'${float(top.amount):.2f}',
                'status': 'Paid'
            })

        return Response({
            'success': True,
            'billing': billing_data,
            'invoices': invoices
        })


class SchoolBillingTopUpView(APIView):
    """
    POST: Top up credits for a school
    """
    permission_classes = [IsSchoolAdminOrOperator]

    def post(self, request, school_id=None):
        from django.db import transaction
        user = request.user
        school = None
        if getattr(user, 'is_authenticated', False) and getattr(user, 'role', None) == 'school_admin':
            school = getattr(user, 'managed_school', None)
        elif school_id:
            try:
                school = School.objects.get(id=school_id)
            except School.DoesNotExist:
                return Response({'error': 'School not found'}, status=status.HTTP_404_NOT_FOUND)
                
        if not school:
            return Response({'error': 'No school linked'}, status=status.HTTP_404_NOT_FOUND)

        percentage = request.data.get('percentage')
        if not percentage:
            return Response({'error': 'percentage is required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            percentage = float(percentage)
        except ValueError:
            return Response({'error': 'Invalid percentage'}, status=status.HTTP_400_BAD_REQUEST)

        subscription = Subscription.objects.filter(organisation=school, status='active').first()
        if not subscription:
            return Response({'error': 'No active subscription to top up'}, status=status.HTTP_400_BAD_REQUEST)

        if not subscription.start_credits:
            start_credits = 100000  # fallback initial assumption if somehow 0
        else:
            start_credits = subscription.start_credits

        amount_to_add = int(start_credits * (percentage / 100.0))
        
        # Estimate cost ($49 for 10%, etc)
        cost_map = {10: 49.00, 25: 99.00, 50: 179.00, 100: 299.00}
        cost = cost_map.get(int(percentage), (percentage / 10) * 49.00)

        # MOCK A PAYMENT BY CREATING A CREDIT TOP AND ADDING CREDITS
        with transaction.atomic():
            CreditTop.objects.create(
                organisation=school,
                transaction_id=f"pi_mock_{timezone.now().timestamp()}",
                user=user,
                credit_add=amount_to_add,
                amount=cost,
                purchase_date=timezone.now().date(),
                payment_status='completed'
            )
            
            # Update Subscription
            subscription.remaining_credits += amount_to_add
            subscription.start_credits += amount_to_add  # Adjust maximum pool
            subscription.save(update_fields=['remaining_credits', 'start_credits'])

        return Response({
            'success': True,
            'message': f'Successfully added {percentage}% credits to subscription.',
            'added_credits': amount_to_add,
            'new_balance': subscription.remaining_credits
        })

class SchoolResetDataView(APIView):
    """
    POST: Reset a school's instance data (Students, Staff, AI Logs, Credit History, Activity)
    """
    permission_classes = [IsSchoolAdminOrOperator]

    def post(self, request, school_id=None):
        from django.db import transaction
        user = request.user
        school = None
        if getattr(user, 'is_authenticated', False) and getattr(user, 'role', None) == 'school_admin':
            school = getattr(user, 'managed_school', None)
        elif school_id:
            try:
                school = School.objects.get(id=school_id)
            except School.DoesNotExist:
                return Response({'error': 'School not found'}, status=status.HTTP_404_NOT_FOUND)
                
        if not school:
            return Response({'error': 'No school linked'}, status=status.HTTP_404_NOT_FOUND)

        try:
            with transaction.atomic():
                # Delete Students
                Student.objects.filter(school=school).delete()
                # Delete Staff (Except current school_admin user if linked)
                Staff.objects.filter(school=school).exclude(school_email=user.email).delete()
                # Delete AILogs for users in this school
                AILog.objects.filter(user__organisation=school).delete()
                # Delete Credit History
                CreditTop.objects.filter(organisation=school).delete()
                # Delete Activity Feed
                Activity.objects.filter(school=school).delete()
                # Delete Usage Logs
                UsageLog.objects.filter(school=school).delete()
                # Delete Subscriptions (maybe clear them and we'll need a new one upon rebranding/onboarding?)
                # For safety, let's keep the core subscription but reset its credits to 0 or its plan's defaults?
                # Actually let's just mark the school as needing orientation again so they can pick a plan/start over
                school.org_orientation = False
                school.save(update_fields=['org_orientation'])

            return Response({
                'success': True,
                'message': 'School instance data has been successfully cleaned and reset.'
            })
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class SchoolOrientationOnboardView(APIView):
    """
    POST: Finalize onboarding orientation, select trial plan, and generate demo data.
    """
    permission_classes = [IsSchoolAdminOrOperator]

    def post(self, request, school_id=None):
        from django.db import transaction
        import random as py_random
        from datetime import date, timedelta
        from authentication.models import User as AuthUser # To properly create mock teachers
        
        user = request.user
        school = None
        if getattr(user, 'is_authenticated', False) and getattr(user, 'role', None) == 'school_admin':
            school = getattr(user, 'managed_school', None)
        elif school_id:
            try:
                school = School.objects.get(id=school_id)
            except School.DoesNotExist:
                return Response({'error': 'School not found'}, status=status.HTTP_404_NOT_FOUND)
                
        if not school:
            return Response({'error': 'No school linked'}, status=status.HTTP_404_NOT_FOUND)

        if school.org_orientation:
            return Response({'error': 'School has already completed orientation setup.'}, status=status.HTTP_400_BAD_REQUEST)

        phone_number = request.data.get('phone_number')
        selected_plan_name = 'Demo Platform' # Force a unified Demo plan for onboarding
        
        # 1. Update School Info
        if phone_number:
            school.contact_phone = phone_number
            # Wait to save org_orientation until the end of transaction

        # 2. Get/Create selected Plan and Subscription
        plan = Plan.objects.filter(name__iexact=selected_plan_name).first()
        if not plan:
            # Create a default Demo mock plan
            plan, _ = Plan.objects.get_or_create(
                name=selected_plan_name,
                defaults={
                    'use_type': 'enterprise',
                    'total_credits': 1000000, # 1M tokens for demo
                    'max_users': 5000,
                    'monthly_price': 0.00
                }
            )

        with transaction.atomic():
            # Create the orientation subscription (Free Trial for 30 days)
            Subscription.objects.filter(organisation=school, status='active').update(status='expired')
            subscription = Subscription.objects.create(
                organisation=school,
                plan=plan,
                status='active',
                max_users=plan.max_users or 500,
                start_credits=plan.total_credits,
                remaining_credits=plan.total_credits,
                billing_start_date=timezone.now().date(),
                billing_end_date=timezone.now().date() + timedelta(days=30)
            )

            # 3. GENERATE DEMO DATA (The "Sample" System)
            
            # --- Students ---
            first_names = ["Sarah", "Mark", "David", "Jessica", "James", "Emily", "Michael", "Sophie", "Robert", "Linda"]
            last_names = ["Johnson", "Davis", "Wilson", "Taylor", "Miller", "Brown", "Jones", "Moore", "White", "Harris"]
            
            students = []
            for i in range(12):
                fname = py_random.choice(first_names)
                lname = py_random.choice(last_names)
                s = Student.objects.create(
                    school=school,
                    first_name=fname,
                    last_name=lname,
                    school_email=f"student_{i+1}@demo.com",
                    student_code=f"STU{str(i+1).zfill(3)}",
                    is_active=True
                )
                students.append(s)

            # --- Teachers (Staff) ---
            teachers = []
            subjects = ["Mathematics", "Physics", "English", "History", "Biology"]
            for i, sub in enumerate(subjects):
                fname = py_random.choice(first_names)
                lname = py_random.choice(last_names)
                email = f"teacher_{i+1}@demo.com"
                
                # Create a User for the Teacher
                u, created = AuthUser.objects.get_or_create(
                    email=email,
                    defaults={
                        'username': email,
                        'first_name': fname,
                        'last_name': lname,
                        'role': 'teacher',
                        'organisation': school,
                        'is_active': True
                    }
                )
                if created: u.set_password('demo123')
                u.save()

                # Create Staff record
                st = Staff.objects.create(
                    school=school,
                    first_name=fname,
                    last_name=lname,
                    school_email=email,
                    role='teacher',
                    subject=sub,
                    is_active=py_random.choice([True, True, True, False]) # Most active
                )
                teachers.append(u)

            # --- AI Activity & Logs ---
            import datetime
            tools = ["Lesson Plan Generator", "Quiz Creator", "Email Draft", "Report Card Helper"]
            all_users_for_logs = teachers + [user] # Include the admin too
            
            for i in range(25):
                t_user = py_random.choice(all_users_for_logs)
                t_tool = py_random.choice(tools)
                t_date = timezone.now() - timedelta(days=py_random.randint(0, 30))
                
                # AILog
                AILog.objects.create(
                    user=t_user,
                    tool=t_tool,
                    title=f"Sample {t_tool} Task",
                    topic=py_random.choice(["Algebra Basics", "Quantum Physics", "Modern History", "Plant Biology"]),
                    prompt="Generate sample content for orientation placeholder.",
                    response="This is a generated response placeholder for the dashboard visualization.",
                    total_tokens=py_random.randint(500, 3000),
                    credits=py_random.randint(50, 200),
                    created_at=t_date
                )
                
                # Activity record (School specific feed)
                Activity.objects.create(
                    school=school,
                    user_name=t_user.get_full_name(),
                    role="Teacher" if t_user in teachers else "Admin",
                    action=f"generated a {t_tool}",
                    tool=t_tool,
                    time="Recently",
                    date=t_date.date(),
                    created_at=t_date
                )

            # --- Credit History (For invoices) ---
            for i in range(2):
                CreditTop.objects.create(
                    subscription=subscription,
                    organisation=school,
                    credit_add=py_random.randint(10000, 50000),
                    purchase_date=timezone.now().date() - timedelta(days=py_random.randint(10, 45)),
                    expiry_date=timezone.now().date() + timedelta(days=365)
                )

            # Mark orientation as complete only after all demo data has been safely seeded
            school.org_orientation = True
            school.save(update_fields=['org_orientation', 'contact_phone'])

        return Response({
            'success': True,
            'message': 'Welcome orientation finished! Your dashboard is now populated with sample demo data and a 30-day Free Trial.',
            'org_orientation': True
        })
