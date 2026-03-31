from rest_framework.test import APITestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from schools.models import School, Staff
import json

User = get_user_model()

class StaffAPITests(APITestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Test School", 
            school_email="test2@school.edu",
            max_students=100
        )
        self.admin_user = User.objects.create_user(
            username="admin_test_2",
            email="admin2@school.edu",
            password="test",
            role="school_admin"
        )
        self.client.force_authenticate(user=self.admin_user)
        self.url = reverse('schools:staff_list_create', kwargs={'school_id': self.school.id})

    def test_staff_crud(self):
        # 1. Create Staff
        data = {
            "name": "Sarah Johnson",
            "email": "sarah.j2@school.edu",
            "subject": "Mathematics",
            "status": "Active",
            "role": "teacher" # adding role as it might be required or default
        }
        res = self.client.post(self.url, data, format='json')
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.data['name'], "Sarah Johnson")
        self.assertEqual(res.data['email'], "sarah.j2@school.edu")
        self.assertEqual(res.data['subject'], "Mathematics")
        self.assertEqual(res.data['status'], "Active")
        
        staff_id = res.data['id']

        # 2. List Staff
        list_res = self.client.get(self.url, format='json')
        self.assertEqual(list_res.status_code, 200)
        self.assertEqual(list_res.data['success'], True)
        self.assertEqual(len(list_res.data['data']['staff']), 1)
        
        # 3. Update Staff
        detail_url = reverse('schools:staff_detail', kwargs={'school_id': self.school.id, 'staff_id': staff_id})
        update_res = self.client.put(detail_url, {"status": "Inactive"}, format='json')
        self.assertEqual(update_res.status_code, 200)
        self.assertEqual(update_res.data['status'], "Inactive")

        # 4. Delete Staff
        del_res = self.client.delete(detail_url)
        self.assertEqual(del_res.status_code, 204)
        
        list_res_after = self.client.get(self.url, format='json')
        self.assertEqual(len(list_res_after.data['data']['staff']), 0)
