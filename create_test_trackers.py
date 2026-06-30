import sys, os, logging
logging.basicConfig(level=logging.INFO)
sys.path.insert(0, '/root/ksushiny_terminatory/vipalina')
os.chdir('/root/ksushiny_terminatory/vipalina')

from tracker_creator import TrackerCreator

print("Инициализация TrackerCreator...", flush=True)
creator = TrackerCreator('vipalina_google_credentials.json')
print(f"auth_mode: {creator.auth_mode}", flush=True)

trackers = [
    ('[club] Тариф VIP', 'Тест Абонемент', 'TEST_ABONEMENT_001', 'Абонемент на год VIP'),
    ('[chatbot-2.0]  VIP с гарантией', 'Тест Чатботы20', 'TEST_CHATBOT20_001', 'Чат-боты 2.0 VIP с гарантией'),
]

for tag, name, gcid, label in trackers:
    print(f'\n=== {label} ===', flush=True)
    try:
        r = creator.create_tracker(student_name=name, course_tag=tag, manager_name='Тест Менеджер', getcourse_id=gcid)
        print(f'URL: {r["url"]}', flush=True)
        print(f'Title: {r["title"]}', flush=True)
        cp = r.get('course_params', {})
        print(f'curator_months={cp.get("original_curator_months","?")}', flush=True)
    except Exception as e:
        import traceback
        print(f'ОШИБКА: {e}', flush=True)
        traceback.print_exc()
