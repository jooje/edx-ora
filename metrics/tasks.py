from controller.models import Submission, SubmissionState, Message
from django.http import HttpResponse
import re
import csv
from metrics.models import StudentCourseProfile, FIELDS_TO_EVALUATE
import numpy
from django.forms.models import model_to_dict
from celery import task
import StringIO
import json
import logging

log = logging.getLogger(__name__)

def sub_commas(text):
    fixed_text=re.sub(","," ",text)
    return fixed_text

def encode_ascii(text):
    return text.encode('ascii', 'ignore')

def set_up_data_dump(locations,name):
    fixed_name=re.sub("[/:]","_",name)

    if isinstance(locations, basestring):
        locations=[locations]

    response = HttpResponse(mimetype='text/csv')
    response['Content-Disposition'] = 'attachment; filename="{0}.csv"'.format(fixed_name)
    string_write = StringIO.StringIO()
    writer = csv.writer(string_write)

    return writer, locations, string_write

def join_if_list(text):
    if isinstance(text,list):
        text=" ".join(text)
    return text

@task
def get_message_in_csv_format(locations, name):
    writer, locations, response = set_up_data_dump(locations, name)
    headers = ["Message Text", "Score", "Location"]
    values = []

    for z in xrange(0,len(locations)):
        location=locations[z]
        fixed_location=re.sub("[/:]","_",location)

        messages=Message.objects.filter(grader__submission__location=location)
        message_score=[message.score for message in messages]
        message_text=[sub_commas(encode_ascii(message.message)) for message in messages]

        for i in xrange(0,len(message_score)):
            values.append([message_text[i], message_score[i], location])

    return write_to_json(headers,values)

def write_to_json(headers, values):
    json_data = []
    for val in values:
        loop_dict = {}
        for i in xrange(0,len(headers)):
            loop_dict.update({headers[i] : val[i]})
        json_data.append(loop_dict)
    return json.dumps(json_data)

@task
def get_data_in_csv_format(locations, name):
    writer, locations, response = set_up_data_dump(locations, name)
    headers = ["Student ID", "Score", "Max Score","Grader Type", "Success", "Submission Text", "Location"]
    values = []
    grader_info = []

    for z in xrange(0,len(locations)):
        location=locations[z]
        fixed_location=re.sub("[/:]","_",location)

        subs=Submission.objects.filter(location=location,state=SubmissionState.finished)
        grader_info=[sub.get_all_successful_scores_and_feedback() for sub in subs]
        bad_list = []
        additional_list = []

        for i in xrange(0,len(grader_info)):
            if isinstance(grader_info[i]['score'], list):
                bad_list.append(i)
                for j in xrange(0,len(grader_info[i]['score'])):
                    new_grader_info = {}
                    for key in grader_info[i]:
                        if isinstance(grader_info[i][key], list):
                            new_grader_info.update({key : grader_info[i][key]})
                        else:
                            new_grader_info.update({key : grader_info[i]})
                    additional_list.append(new_grader_info)

        grader_info = [grader_info[i] for i in xrange(0,len(grader_info)) if i not in bad_list]
        grader_info += additional_list

        grader_type=[grade['grader_type'] for grade in grader_info]
        score=[numpy.median(grade['score']) for grade in grader_info]
        feedback=[sub_commas(encode_ascii(join_if_list(grade['feedback']))) for grade in grader_info]
        success=[grade['success'] for grade in grader_info]
        submission_text=[sub_commas(encode_ascii(sub.student_response)) for sub in subs]
        max_score=[sub.max_score for sub in subs]
        student_ids = [grade['student_id'] for grade in grader_info]

        for i in xrange(0,len(grader_info)):
            values.append([student_ids[i], score[i], max_score[i], grader_type[i], success[i], submission_text[i], location] + grader_info[i]['rubric_scores'])
    if len(grader_info) > 0:
        rubric_headers = grader_info[0]['rubric_headers']
        for i in xrange(0,len(rubric_headers)):
            rubric_headers[i] = "rubric_{0}".format(rubric_headers[i])
            if rubric_headers[i] in headers:
                rubric_headers[i] = "{0}.1".format(rubric_headers[i])
        headers+=rubric_headers
    return write_to_json(headers,values)

@task
def get_student_data_in_csv_format(locations, name):
    writer, locations, response = set_up_data_dump(locations, name)
    headers = FIELDS_TO_EVALUATE
    values = []

    for z in xrange(0,len(locations)):
        location=locations[z]
        fixed_location=re.sub("[/:]","_",location)

        student_course_profiles=StudentCourseProfile.objects.filter(course_id=location)
        student_course_profiles_count = student_course_profiles.count()

        for i in xrange(0,student_course_profiles_count):
            field_values = []
            all_zeros = True
            scp_dict = model_to_dict(student_course_profiles[i])
            for m in xrange(0,len(FIELDS_TO_EVALUATE)):
                scp_val = scp_dict.get(FIELDS_TO_EVALUATE[m], 0)
                field_values.append(scp_val)
                if scp_val!=0:
                    all_zeros = False
            if not all_zeros:
                values.append(field_values)

    return write_to_json(headers,values)