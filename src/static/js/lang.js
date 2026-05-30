


// function toggleLanguage() {
//     const currentLang = localStorage.getItem('lang') || 'ar';
//     const newLang = currentLang === 'ar' ? 'en' : 'ar';

//     // خزّن اللغة الجديدة
//     localStorage.setItem('lang', newLang);

//     // غيّر الأيقونة
//     const icon = document.getElementById("langIcon");
//     icon.textContent = newLang === 'ar' ? '🇸🇦' : '🇬🇧';

//     // غيّر اتجاه الصفحة (اختياري)
//     document.documentElement.setAttribute('lang', newLang);
//     document.documentElement.dir = newLang === 'ar' ? 'rtl' : 'ltr';
//   }

//   // عند تحميل الصفحة طبّق التفضيل المخزن
//   document.addEventListener('DOMContentLoaded', () => {
//     const savedLang = localStorage.getItem('lang') || 'ar';
//     const icon = document.getElementById("langIcon");
//     icon.textContent = savedLang === 'ar' ? '🇸🇦' : '🇬🇧';

//     document.documentElement.setAttribute('lang', savedLang);
//     document.documentElement.dir = savedLang === 'ar' ? 'rtl' : 'ltr';
//   });