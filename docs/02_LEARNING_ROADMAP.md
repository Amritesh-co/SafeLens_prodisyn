# Learning Roadmap: Building Django APIs from Scratch

To build a project like "Worker Safety API" from scratch, you need to understand several layers of technology. Here is a curated list of documentation and concepts you should read in order.

## 1. The Foundation: Python & Django
Before the API part, you need to understand the web framework.

### Concepts to Learn:
-   **MVC Pattern (Model-View-Controller)**: Django calls this MTV (Model-Template-View), but the concept is the same. Separation of data (Model), logic (View), and display (Template/Serializer).
-   **ORM (Object-Relational Mapping)**: How Python classes map to database tables.

### Documentation to Read:
1.  **[Official Django Tutorial (Part 1-4)](https://docs.djangoproject.com/en/stable/intro/tutorial01/)**:
    -   *Crucial for*: Understanding `models.py`, `views.py`, and `urls.py`.
2.  **[Django Models](https://docs.djangoproject.com/en/stable/topics/database/models/)**:
    -   *Crucial for*: Defining your data structure.

---

## 2. The Core: Django REST Framework (DRF)
This is the library that powers the API part of this project.

### Concepts to Learn:
-   **Serialization**: converting complex data (like QuerySets) into native Python datatypes (like dictionaries) that can then be easily rendered into JSON.
-   **ViewSets & Routers**: The "magic" that automatically creates URL patterns for you.

### Documentation to Read:
1.  **[DRF Tutorial (Quickstart)](https://www.django-rest-framework.org/tutorial/quickstart/)**:
    -   *Crucial for*: Getting an API up and running in minutes.
2.  **[Serializers](https://www.django-rest-framework.org/api-guide/serializers/)**:
    -   *Crucial for*: Understanding how `api/serializers.py` works.
3.  **[ViewSets](https://www.django-rest-framework.org/api-guide/viewsets/)**:
    -   *Crucial for*: Understanding `api/views.py`.

---

## 3. Database Integration (Legacy Databases)
Since this project connects to an *existing* database (`managed = False`), this is a specific advanced topic you utilized.

### Concepts to Learn:
-   **Introspection (`inspectdb`)**: How Django can "read" your existing database and write the models for you.
-   **Unmanaged Models**: what `managed = False` means (Django won't create/delete tables).

### Documentation to Read:
1.  **[Integrating with a Legacy Database](https://docs.djangoproject.com/en/stable/howto/legacy-databases/)**:
    -   *Crucial for*: Understanding why your `models.py` looks the way it does.

---

## 4. API Design Standards
To make your API usable by others (like frontend developers), you need to follow standards.

### Concepts to Learn:
-   **REST (Representational State Transfer)**: Using HTTP methods correctly (`GET` for reading, `POST` for creating).
-   **JSON Structure**: How to nest data (e.g., putting `camera` details inside an `event` object).
-   **Filtering**: How URL parameters like `?date=2023-01-01` work.

---

## Summary Checklist
If you can answer these questions, you are ready to build this project:
-   [ ] **Python**: Can I write a class and a function?
-   [ ] **Django Model**: Can I define a `class Person(models.Model)`?
-   [ ] **Django Manager**: Do I know what `Person.objects.filter(name="John")` does?
-   [ ] **Serializer**: Do I know how to turn that `Person` object into `{'name': 'John'}`?
-   [ ] **View**: Do I know how to return that JSON to a browser request?
