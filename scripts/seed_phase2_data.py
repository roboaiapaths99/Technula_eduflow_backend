import urllib.request
import json

# 1. Create a PTC event
event_payload = {
    'school_id': 'c2b44421-9ec8-4461-ac02-1cd22665a124',
    'title': 'Term 2 Board Readiness Parent-Teacher Conference',
    'description': 'One-on-one academic consultation discussing Class 10 CBSE Board strategy and remedial planning.',
    'event_date': '2026-09-20',
    'start_time': '09:00',
    'end_time': '12:00',
    'slot_duration_mins': 15,
    'grade': '10',
    'room_or_link': 'Room 102 (Academic Block)'
}
req = urllib.request.Request('http://localhost:8000/ptc/events', data=json.dumps(event_payload).encode(), headers={'Content-Type': 'application/json'})
res = urllib.request.urlopen(req)
print('PTC Event Created:', res.read().decode())

# 2. Apply for a Bonafide Certificate for Aarav
cert_payload = {
    'student_id': '043b8f1a-f30b-4066-b0ab-6214fc9fd7dd',
    'certificate_type': 'BONAFIDE',
    'purpose_reason': 'Passport renewal and National Science Olympiad verification.',
    'delivery_mode': 'ONLINE_APP',
    'parent_user_id': 'd5931b94-b6a5-4f80-a0a4-40177ac65ab0'
}
req2 = urllib.request.Request('http://localhost:8000/certificates/apply', data=json.dumps(cert_payload).encode(), headers={'Content-Type': 'application/json'})
res2 = urllib.request.urlopen(req2)
r_data = json.loads(res2.read().decode())
print('Certificate Applied:', r_data)

# 3. Approve the certificate
req_id = r_data['request_id']
req3 = urllib.request.Request(f'http://localhost:8000/certificates/requests/{req_id}/approve', data=json.dumps({'approved_by': 'Dr. Alok Verma (Principal)'}).encode(), headers={'Content-Type': 'application/json'})
res3 = urllib.request.urlopen(req3)
print('Certificate Approved:', res3.read().decode())
