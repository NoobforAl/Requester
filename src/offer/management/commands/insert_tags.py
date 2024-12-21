from django.core.management.base import BaseCommand
from offer.models import Tag


class Command(BaseCommand):
    help = 'Insert predefined tags into the database'

    def handle(self, *args, **kwargs):
        tags = [
            "جنگو",
            "پایتون",
            "مهندس نرم‌افزار",
            "دانشمند داده",
            "توسعه‌دهنده وب",
            "توسعه‌دهنده بک‌اند",
            "توسعه‌دهنده فرانت‌اند",
            "توسعه‌دهنده فول استک",
            "مهندس DevOps",
            "مهندس یادگیری ماشین",
            "مدیر سیستم",
            "مدیر پایگاه داده",
            "معمار نرم‌افزار",
            "مهندس QA",
            "توسعه‌دهنده موبایل",
            "طراح UX/UI",
            "مدیر محصول",
            "نویسنده فنی",
            "متخصص پشتیبانی IT",
            "مهندس شبکه",
            "مهندس ابر",
            "توسعه‌دهنده نرم‌افزار",
            "برنامه‌نویسی",
            "طراحی نرم‌افزار",
            "تحلیل داده",
            "مدل‌سازی",
            "مدیر پروژه",
            "رهبری",
            "برنامه‌ریزی پروژه",
            "زیرساخت ابری",
            "اتوماسیون",
            "طراحی تعاملی",
            "طراح تجربه کاربری",
            "طراح رابط کاربری",
            "توسعه‌دهنده فرانت‌اند",
            "جاوااسکریپت",
            "ری‌اکت",
            "HTML/CSS",
            "توسعه‌دهنده بک‌اند",
            "پایتون",
            "API",
            "توسعه‌دهنده موبایل",
            "اندروید",
            "iOS",
            "توسعه اپلیکیشن موبایل",
            "مدیریت سیستم",
            "زیرساخت IT",
            "پشتیبانی شبکه",
            "تحلیل امنیت سایبری",
            "امنیت IT",
            "حفاظت از اطلاعات",
            "تحلیل تهدیدات"
        ]

        if Tag.objects.count() > 0:
            self.stdout.write(
                self.style.WARNING('Tags already exist in the database.')
            )
            return

        for tag_name in tags:
            tag, created = Tag.objects.get_or_create(name=tag_name)

            if created:
                self.stdout.write(self.style.SUCCESS(
                    f'Successfully added tag: {tag_name}'))
            else:
                self.stdout.write(self.style.WARNING(
                    f'Tag already exists: {tag_name}'))
