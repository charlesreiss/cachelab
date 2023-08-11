# Cachelab

This is a small web application for asking some CPU cache related questions.

Two sets of questions are asked:

1.  given some parameters of a memory cache, filling in the other parameters
2.  given some parameters of a memory cache and a series of accesses, identify which are hits and misses, and for the misses, identify what is evicted in order to bring in the new item

The tool requires three sets of questions to be answered of the first type and one of the second type. Students can keep trying new questions until they get all questions correct.

# Quick demo

Setup a Python environment with Django and dateutils installed.

Run `./run-demo.sh migrate`, then `./run-demo.sh make_user username password`, then `./run-demo.sh`.
Then go `http://localhost:8888/` and login with the username you created.

# Setup

This program is a Django web application. To use it, first:

*  Figure out how you're handling authentication, see [the Authentication section below](#Authentication)
*  Edit `cachelabweb/settings.py` to change `ALLOWED_HOSTS` and `COURSE_WEBSITE` and (if you are using
   external authentication as described below) `LOGIN_URL`
*  Do any customization of the questions you desire.

Then,you can run it as a standalone web application using `python manage.py runserver 127.0.0.1:8888` (to bind to port 8888 on localhost).
When not testing, I ran it using Nginx to act as an HTTPS server which acted as a reverse proxy to a uwsgi server as the backend. Configuration files used are in `config-templates`.

# Authentication

## manually created accounts

`manage.py` has commands:

*  `make_user USERNAME PASSWORD` subcommand which can create users with a particular username and password.
*  `make_staff USERNAME` to mark a user as staff (gives access to some administrative functionality via web interface)
*  `make_not_staff USERNAME` to mark a user as not-staff

## via external authentication

As this was used at the University of Virginia, this web application relies on logins being forwarded from another website for authentication (rather
than tying directly with a single-sign on system). The scripts used in Spring 2018 at the University of Virginia are in the `config-templates` directory:

To make this work, create a `cachelab/secret_settings.py` which contains code like

    SECRET_KEY = '...'

. Then, you could use the PHP script `config-templates/cachelab.php` (or the `-prompt` version is used) by modifying:

*  the URL in the `<form>` tag to point to the ocation running the web application
*  the `$key` variable to have the same value as the secret key in `SECRET_KEY` in `secret_settings.py`

along with a `staff.php` script that sets:

*  `$user` to the user ID of the user. This is the ID that will be used when extracting grading information from the web application. At the UVa, the PHP script ran an Apache webserver using the Shibboleth single-sign on authentication module, so `$user` could be set `$PHP_AUTH_USER`.
*  `$isstaff` set to true if the user is course staff, false otherwise. Setting this flag on login enables debugging information and access to grades.

## extending to add alternate approaches

The authentication uses django built-in account support, so an tools that work with django's builtin
accounts should be able to provide alternate authentication methods.

The built-in `make_staff` command works by checking a table of staff users setup
in `myauth.models`. The actual code in
`cachelab` checks whether users are staff by looking at the `is_staff` and `cachelab_is_staff` session variable.

# General code organizatoin

The actual exercises and the index page for them are in the `cachelab` module. 

The `myauth` module handles authentication. `cachelab.root_urls` sets up routing to use `myauth` alongside
`cachelab`'s exercises. If you want to use the exercises as part of a larger django app,
`cachelab.urls` has self-contained URLs you can use django's `include()` operation to specify.

# Modifying the questions

Most of the code that generates the questions is in `cachelab/models.py` (with the corresponding HTML generation and form processing code in
`cachelab/views.py`). To change how random access patterns are generated edit the default parameters of the `random` method of `CachePattern`,
and the `random_parameters_for_pattern` function. To change how random cache parameters are selected for parameter
fill-in-the-blank questions, change the default parameters of the `random` method of `CacheParameters`.

To change the number of cache parametetr questions required before the tool indicates the user is done, change `NEEDED_PARAMETER_PERFECT` in
`cachelab/views.py`.

# Retrieving grades

If you login as staff, there is an option to retrieve grades as a CSV file. Alternately, you can use the dump_grades command of manage.py

The grade formula is hard-coded in `get_scores_csv`, and
gives 5 points for the parameter questions and 5 points for the pattern questions, with a minimum score of 5 for students who get
at least 2 points on their best 3 parameter questions (counting each question as 1 point). When retrieving the CSV file, you are required
to entire a due time, the CSV file retrieved will ignore all work done after that due time. The dump_grades command should support
specifying individual exceptions for students.

# Missing features / regrets

*  Students often get confused between a cache miss causing something to be evicted and that miss being a conflict miss. To help with this, it might be a good idea to ask whether each cache miss is a compulsory miss or not.

*  I didn't take advantage of Django's form generation support, which probably cost me a lot of time and elegance.
