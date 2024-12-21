from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from offer.models import Offer


class Command(BaseCommand):
    help = 'Insert multiple offers into the database,'
    ' creating users if they do not exist'

    def handle(self, *args, **kwargs):
        # Sample data for offers
        offers_to_insert = [
            {
                'username': 'alice',
                'company_name': 'گوگل',
                'company_email': 'alice@google.com',
                'detail': (
                    'توسعه راه‌حل‌های نوآورانه در گوگل، '
                    'تخصص در ابزارهای مبتنی بر '
                    'هوش مصنوعی و خدمات ابری '
                    'برای افزایش بهره‌وری در بخش‌های مختلف.'
                ),
                'password': 'password123',
            },
            {
                'username': 'frank',
                'company_name': 'مایکروسافت',
                'company_email': 'frank@microsoft.com',
                'detail': (
                    'نوآوری در راه‌حل‌ها برای نرم‌افزارهای سازمانی، '
                    'توسعه ابزارهای پیشرفته برای کسب‌وکارها '
                    'برای ساده‌سازی عملیات‌ها، '
                    'با تمرکز بر خدمات ابری و امنیت سازمانی.'
                ),
                'password': 'password123',
            },
            {
                'username': 'grace',
                'company_name': 'آمازون',
                'company_email': 'grace@amazon.com',
                'detail': (
                    'بهینه‌سازی لجستیک برای سیستم‌های تحویل بهتر، '
                    'پیاده‌سازی هوش مصنوعی و یادگیری ماشین برای '
                    'ایجاد زنجیره‌های تأمین کارآمدتر و '
                    'راه‌حل‌های تحویل سریع‌تر.'
                ),
                'password': 'password123',
            },
            {
                'username': 'heidi',
                'company_name': 'اپل',
                'company_email': 'heidi@apple.com',
                'detail': (
                    'طراحی رابط‌های '
                    'کاربری شهودی برای اپلیکیشن‌های iOS،'
                    ' افزایش تعامل کاربر از طریق اصول طراحی ساده '
                    'و یکپارچگی بدون درز با اکوسیستم اپل.'
                ),
                'password': 'password123',
            },
            {
                'username': 'ivan',
                'company_name': 'فیس‌بوک',
                'company_email': 'ivan@facebook.com',
                'detail': (
                    'ساخت ابزارهای تعامل در شبکه‌های اجتماعی برای '
                    'بهبود تعامل کاربران، توسعه الگوریتم‌ها '
                    'برای محتوای شخصی‌سازی‌شده و ویژگی‌های مدیریت جوامع.'
                ),
                'password': 'password123',
            },
            {
                'username': 'judy',
                'company_name': 'نت‌فلیکس',
                'company_email': 'judy@netflix.com',
                'detail': (
                    'ایجاد سیستم‌های توصیه‌گر برای فیلم‌ها و '
                    'برنامه‌های تلویزیونی، بهبود قابلیت نت‌فلیکس '
                    'برای پیشنهاد محتوای شخصی‌سازی‌شده '
                    'بر اساس ترجیحات و عادات تماشای کاربران.'
                ),
                'password': 'password123',
            },
        ]

        if Offer.objects.count() > 0:
            self.stdout.write(
                self.style.WARNING('Offers already exist in the database.')
            )
            return

        for offer_data in offers_to_insert:
            user, created = User.objects.get_or_create(
                username=offer_data['username'],
                defaults={
                    'email': offer_data['company_email'],
                    'password': offer_data['password'],
                }
            )
            if created:
                user.set_password(offer_data['password'])
                user.save()
                self.stdout.write(self.style.SUCCESS(
                    f'Successfully created user: {offer_data["username"]}'))
            else:
                self.stdout.write(self.style.WARNING(
                    f'User already exists: {offer_data["username"]}'))

            offer, created = Offer.objects.get_or_create(
                user=user,
                company_name=offer_data['company_name'],
                company_email=offer_data['company_email'],
                detail=offer_data['detail']
            )
            if created:
                self.stdout.write(self.style.SUCCESS(
                    f'Successfully added offer for: {offer_data["username"]}'))
            else:
                self.stdout.write(self.style.WARNING(
                    f'Offer already exists for: {offer_data["username"]}'))
