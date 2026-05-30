# Templates Patterns

## 1) القوائم – base_list.html
- القالب: web/templates/web/base_list.html
- يستخدم مع المتغيّر: page_obj
- مثال:

{% raw %}
{% extends "web/base_list.html" %}
{% block page_title %}قائمة المستخدمين{% endblock %}
{% block table_head %} ... {% endblock %}
{% block table_body %} ... {% endblock %}
{% endraw %}

## 2) الفورم – base_form.html
- القالب: web/templates/web/base_form.html
- يعتمد على: form
- مثال:

{% raw %}
{% extends "web/base_form.html" %}
{% block page_title %}إضافة مستخدم{% endblock %}
{% endraw %}

## 3) التفاصيل – base_detail.html
- القالب: web/templates/web/base_detail.html
- البلوك المهم: detail_content
