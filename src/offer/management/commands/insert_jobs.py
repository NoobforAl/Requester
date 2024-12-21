from django.core.management.base import BaseCommand
from offer.models import Job, Offer, Tag


class Command(BaseCommand):
    help = 'Insert multiple jobs into the database'

    def handle(self, *args, **kwargs):
        jobs_to_insert = [
            {
                'job_name': 'Software Engineer',
                'detail': (
                    'توسعه و نگهداری برنامه‌های نرم‌افزاری. '
                    'طراحی و پیاده‌سازی سیستم‌های '
                    'نرم‌افزاری مقیاس‌پذیر و مطمئن، '
                    'ارزیابی نیازهای کاربران و بهینه‌سازی عملکرد برنامه‌ها.'
                ),
                'tags': [
                    'مهندس نرم‌افزار',
                    'توسعه‌دهنده نرم‌افزار',
                    'برنامه‌نویسی',
                    'طراحی نرم‌افزار',
                ],
                'offer': 'alice'
            },
            {
                'job_name': 'Data Scientist',
                'detail': (
                    'تحلیل و تفسیر مجموعه داده‌های '
                    'پیچیده برای استخراج اطلاعات و روندها. '
                    'استفاده از تکنیک‌های یادگیری ماشین و'
                    ' مدل‌سازی پیش‌بینی برای حل مسائل تجاری و علمی.'
                ),
                'tags': [
                    'دانشمند داده',
                    'تحلیل داده',
                    'یادگیری ماشین',
                    'مدل‌سازی',
                ],
                'offer': 'bob',
            },
            {
                'job_name': 'Project Manager',
                'detail': (
                    'مدیریت پروژه‌ها و اطمینان از تحویل به '
                    'موقع و مطابق با استانداردهای کیفیت. '
                    'رهبری تیم‌های چندوظیفه‌ای و هماهنگی '
                    'با ذینفعان برای پیشبرد اهداف پروژه.'
                ),
                'tags': ['مدیر پروژه', 'مدیریت', 'رهبری', 'برنامه‌ریزی پروژه'],
                'offer': 'charlie',
            },
            {
                'job_name': 'DevOps Engineer',
                'detail': (
                    'کار بر روی CI/CD، اتوماسیون فرآیندهای توسعه و '
                    'استقرار نرم‌افزار، '
                    'و همچنین مدیریت و بهینه‌سازی زیرساخت‌های ابری و سرور.'
                ),
                'tags': ['مهندس DevOps', 'زیرساخت ابری', 'CI/CD', 'اتوماسیون'],
                'offer': 'dave',
            },
            {
                'job_name': 'UI/UX Designer',
                'detail': (
                    'طراحی رابط‌های کاربری کاربرپسند '
                    'و بهینه‌سازی تجربه کاربری. '
                    'استفاده از اصول طراحی برای ایجاد '
                    'تجربه‌ای روان و جذاب برای کاربران.'
                ),
                'tags': [
                    'طراحی UI/UX',
                    'طراح تجربه کاربری',
                    'طراح رابط کاربری',
                    'طراحی تعاملی',
                ],
                'offer': 'eve',
            },
            {
                'job_name': 'Frontend Developer',
                'detail': (
                    'ساخت برنامه‌های وب واکنش‌گرا با استفاده از '
                    'تکنولوژی‌های مختلف مثل جاوااسکریپت و ری‌اکت. '
                    'تمرکز بر تجربه کاربری و رابط‌های کاربری سریع و واکنش‌گرا.'
                ),
                'tags': [
                    'توسعه‌دهنده فرانت‌اند',
                    'جاوااسکریپت', 'ری‌اکت',
                    'HTML/CSS',
                ],
                'offer': 'frank',
            },
            {
                'job_name': 'Backend Developer',
                'detail': (
                    'ایجاد و نگهداری برنامه‌های سمت سرور با '
                    'استفاده از فریم‌ورک‌های مختلف مانند جنگو. '
                    'مدیریت پایگاه‌داده‌ها، '
                    'بهینه‌سازی عملکرد و ایجاد APIهای مقیاس‌پذیر.'
                ),
                'tags': ['توسعه‌دهنده بک‌اند', 'پایتون', 'جنگو', 'API'],
                'offer': 'grace',
            },
            {
                'job_name': 'Mobile Developer',
                'detail': (
                    'توسعه برنامه‌ها برای پلتفرم‌های موبایل با '
                    'استفاده از فناوری‌های مختلف مانند اندروید و iOS. '
                    'بهینه‌سازی عملکرد و تجربه کاربری در دستگاه‌های موبایل.'
                ),
                'tags': [
                    'توسعه‌دهنده موبایل',
                    'اندروید',
                    'iOS',
                    'توسعه اپلیکیشن موبایل',
                ],
                'offer': 'heidi',
            },
            {
                'job_name': 'System Administrator',
                'detail': (
                    'مدیریت و نگهداری زیرساخت‌های IT شامل شبکه‌ها، سرورها و '
                    'پایگاه‌های داده. '
                    'پشتیبانی از سیستم‌ها و '
                    'تضمین عملکرد صحیح و بهینه سیستم‌ها.'
                ),
                'tags': [
                    'مدیر سیستم',
                    'مدیریت سیستم',
                    'زیرساخت IT',
                    'پشتیبانی شبکه',
                ],
                'offer': 'ivan',
            },
            {
                'job_name': 'Cybersecurity Analyst',
                'detail': (
                    'حفاظت از سیستم‌ها در برابر '
                    'نفوذهای امنیتی و تهدیدات سایبری. '
                    'تحلیل آسیب‌پذیری‌ها و پیاده‌سازی تدابیر '
                    'امنیتی برای حفظ امنیت اطلاعات.'
                ),
                'tags': [
                    'تحلیل امنیت سایبری',
                    'امنیت IT',
                    'حفاظت از اطلاعات',
                    'تحلیل تهدیدات',
                ],
                'offer': 'judy',
            },
        ]

        if Job.objects.count() > 0:
            self.stdout.write(
                self.style.ERROR('Jobs already exist in the database.')
            )
            return

        for job_data in jobs_to_insert:
            offer = Offer.objects.filter(
                user__username=job_data['offer']).first()
            if not offer:
                self.stdout.write(self.style.ERROR(
                    f'Offer not found for user: {job_data["offer"]}'))
                continue

            tag_objects = []
            for tag_name in job_data['tags']:
                tag, created = Tag.objects.get_or_create(name=tag_name)
                tag_objects.append(tag)

            job, created = Job.objects.get_or_create(
                job_name=job_data['job_name'],
                offer=offer,
                defaults={
                    'detail': job_data['detail'],
                }
            )

            job.tags.set(tag_objects)

            if created:
                self.stdout.write(self.style.SUCCESS(
                    f'Successfully added job: {job_data["job_name"]}'))
            else:
                self.stdout.write(self.style.WARNING(
                    f'Job already exists: {job_data["job_name"]}'))
