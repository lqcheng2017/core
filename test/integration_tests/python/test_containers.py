import bson


def test_switching_project_between_groups(data_builder, as_admin):
    group_1 = data_builder.create_group()
    group_2 = data_builder.create_group()
    project = data_builder.create_project(group=group_1)

    r = as_admin.put('/projects/' + project, json={'group': group_2})
    assert r.ok

    r = as_admin.get('/projects/' + project)
    assert r.ok
    assert r.json()['group'] == group_2

    # Test switching to nonexisting project
    r = as_admin.put('/projects/' + project, json={'group': "doesnotexist"})
    assert r.status_code == 404


def test_switching_session_between_projects(data_builder, as_admin):
    project_1 = data_builder.create_project()
    project_2 = data_builder.create_project()
    session = data_builder.create_session(project=project_1)

    r = as_admin.put('/sessions/' + session, json={'project': project_2})
    assert r.ok

    r = as_admin.get('/sessions/' + session)
    assert r.ok
    assert r.json()['project'] == project_2

    # Test switching to nonexisting project
    r = as_admin.put('/sessions/' + session, json={'project': "000000000000000000000000"})
    assert r.status_code == 404


def test_switching_acquisition_between_sessions(data_builder, as_admin):
    session_1 = data_builder.create_session()
    session_2 = data_builder.create_session()
    acquisition = data_builder.create_acquisition(session=session_1)

    r = as_admin.put('/acquisitions/' + acquisition, json={'session': session_2})
    assert r.ok

    r = as_admin.get('/acquisitions/' + acquisition)
    assert r.ok
    assert r.json()['session'] == session_2

    # Test switching to nonexisting project
    r = as_admin.put('/acquisitions/' + acquisition, json={'session': "000000000000000000000000"})
    assert r.status_code == 404


def test_project_template(data_builder, file_form, as_admin):
    project = data_builder.create_project()
    project2 = data_builder.create_project()
    session = data_builder.create_session(subject={'code': 'compliant'})
    # NOTE adding acquisition_1 to cover code that's skipping non-matching containers
    acquisition_1 = data_builder.create_acquisition(label='non-compliant')
    acquisition_2 = data_builder.create_acquisition(label='compliant')
    assert as_admin.post('/acquisitions/' + acquisition_2 + '/tags', json={'value': 'compliant'}).ok
    assert as_admin.post('/acquisitions/' + acquisition_2 + '/files', files=file_form('non-compliant.txt')).ok
    assert as_admin.post('/acquisitions/' + acquisition_2 + '/files', files=file_form('compliant1.csv')).ok
    assert as_admin.post('/acquisitions/' + acquisition_2 + '/files', files=file_form('compliant2.csv')).ok

    # test the session before setting the template
    r = as_admin.get('/sessions/' + session)
    assert r.ok
    assert 'project_has_template' not in r.json()

    # create template for the project
    r = as_admin.post('/projects/' + project + '/template', json={
        'session': {'subject': {'code': '^compliant$'}},
        'acquisitions': [{
            'minimum': 1,
            'label': '^compliant$',
            'tags': '^compliant$',
            'files': [{
                'minimum': 2,
                'mimetype': 'text/csv',
            }]
        }]
    })
    assert r.ok
    assert r.json()['modified'] == 1

    # create template for the project2
    r = as_admin.post('/projects/' + project2 + '/template', json={
        'session': {'subject': {'code': '^compliant$'}},
        'acquisitions': [{
            'minimum': 100, # Session won't comply
            'label': '^compliant$',
            'tags': '^compliant$',
            'files': [{
                'minimum': 2,
                'mimetype': 'text/csv',
            }]
        }]
    })


    # test session compliance
    r = as_admin.get('/sessions/' + session)
    assert r.ok
    assert r.json()['project_has_template']

    def satisfies_template():
        r = as_admin.get('/sessions/' + session)
        assert r.ok
        return r.json()['satisfies_template']

    # test that missing any single requirement breaks compliance
    # session.subject.code
    assert satisfies_template()
    assert as_admin.put('/sessions/' + session, json={'subject': {'code': 'non-compliant'}}).ok
    assert not satisfies_template()
    assert as_admin.put('/sessions/' + session, json={'subject': {'code': 'compliant'}}).ok

    # test that moving session to another project correctly updates session.satisfies_template
    assert satisfies_template()
    assert as_admin.put('/sessions/' + session, json={'project': project2})
    assert not satisfies_template()
    assert as_admin.put('/sessions/' + session, json={'project': project})
    assert satisfies_template()

    # test moving session to project without template
    assert as_admin.delete('/projects/' + project2 + '/template')
    r = as_admin.put('/sessions/' + session, json={'project': project2})
    assert r.ok
    r = as_admin.get('/sessions/' + session)
    assert r.ok
    assert 'project_has_template' not in r.json()
    assert 'satisfies_template' not in r.json()
    assert as_admin.put('/sessions/' + session, json={'project': project})

    # archived acqusitions don't affect session compliance
    assert satisfies_template()
    # Hide Acq_2 so that no acquisition in the session are compliant
    assert as_admin.put('/acquisitions/' + acquisition_2, json={'archived': True}).ok
    assert not satisfies_template()
    assert as_admin.put('/acquisitions/' + acquisition_2, json={'archived': False})

    # acquisitions.label
    assert satisfies_template()
    assert as_admin.put('/acquisitions/' + acquisition_2, json={'label': 'non-compliant'}).ok
    assert not satisfies_template()
    assert as_admin.put('/acquisitions/' + acquisition_2, json={'label': 'compliant'}).ok

    # acquisitions.tags
    assert satisfies_template()
    assert as_admin.delete('/acquisitions/' + acquisition_2 + '/tags/compliant').ok
    # TODO figure out why removing the tag does not break compliance
    # assert not satisfies_template()
    assert as_admin.post('/acquisitions/' + acquisition_2 + '/tags', json={'value': 'compliant'}).ok

    # acquisitions.files.minimum
    assert satisfies_template()
    assert as_admin.delete('/acquisitions/' + acquisition_2 + '/files/compliant2.csv').ok
    assert not satisfies_template()
    assert as_admin.post('/acquisitions/' + acquisition_2 + '/files', files=file_form('compliant2.csv')).ok

    # acquisitions.minimum
    assert satisfies_template()
    assert as_admin.delete('/acquisitions/' + acquisition_2)
    assert not satisfies_template()

    # delete project template
    r = as_admin.delete('/projects/' + project + '/template')
    assert r.ok

    r = as_admin.get('/sessions/' + session)
    assert r.ok
    assert 'project_has_template' not in r.json()


def test_get_all_containers(data_builder, as_public):
    project_1 = data_builder.create_project()
    project_2 = data_builder.create_project()
    session = data_builder.create_session(project=project_1)

    # get all projects w/ info=true
    r = as_public.get('/projects', params={'info': 'true'})
    assert r.ok

    # get all projects w/ counts=true
    r = as_public.get('/projects', params={'counts': 'true'})
    assert r.ok
    assert all('session_count' in proj for proj in r.json())

    # get all projects w/ stats=true
    r = as_public.get('/projects', params={'stats': 'true'})
    assert r.ok

    # get all projects w/ permissions=true
    r = as_public.get('/projects', params={'permissions': 'true'})
    assert r.ok
    assert all('permissions' in proj for proj in r.json())

    # get all projects w/ join_avatars=true
    r = as_public.get('/projects', params={'join_avatars': 'true'})
    assert r.ok
    assert all('avatar' in perm for proj in r.json() for perm in proj['permissions'])

    # get all sessions for project w/ measurements=true and stats=true
    r = as_public.get('/projects/' + project_1 + '/sessions', params={
        'measurements': 'true',
        'stats': 'true'
    })
    assert r.ok


def test_get_all_for_user(as_admin, as_public):
    r = as_admin.get('/users/self')
    user_id = r.json()['_id']

    # try to get containers for user w/o logging in
    r = as_public.get('/users/' + user_id + '/sessions')
    assert r.status_code == 403

    # get containers for user
    r = as_admin.get('/users/' + user_id + '/sessions')
    assert r.ok


def test_get_container(data_builder, default_payload, file_form, as_drone, as_admin, as_public, api_db):
    project = data_builder.create_project()
    session = data_builder.create_session()
    gear_doc = default_payload['gear']['gear']
    gear_doc['inputs'] = {
        'csv': {
            'base': 'file'
        }
    }
    gear = data_builder.create_gear(gear=gear_doc)

    # upload files for testing join=origin
    # Origin.user upload (the jobs below also reference it)
    as_admin.post('/projects/' + project + '/files', files=file_form(
        'user.csv', meta={'name': 'user.csv'}))
    job_1 = data_builder.create_job(inputs={
        'user': {'type': 'project', 'id': project, 'name': 'user.csv'}})

    # Origin.job upload (requires as_drone)
    as_drone.post('/engine',
        params={'level': 'project', 'id': project, 'job': job_1},
        files=file_form('job_1.csv', meta={'project': {'files': [{'name': 'job_1.csv'}]}}))
    job_2 = data_builder.create_job(inputs={
        'user': {'type': 'project', 'id': project, 'name': 'user.csv'}})

    # additional Origin.job upload for testing join=origin_job_gear_name gear name caching
    as_drone.post('/engine',
        params={'level': 'project', 'id': project, 'job': job_2},
        files=file_form('job_2.csv', meta={'project': {'files': [{'name': 'job_2.csv'}]}}))

    # upload file and unset origin to mimic missing origin scenario
    as_admin.post('/projects/' + project + '/files', files=file_form(
        'none.csv', meta={'name': 'none.csv'}))
    api_db.projects.update(
        {'_id': bson.ObjectId(project), 'files.name': 'none.csv'},
        {'$unset': {'files.$.origin': ''}})

    # try to get container w/ non-existent object id
    r = as_public.get('/projects/000000000000000000000000')
    assert r.status_code == 404

    # get container
    r = as_public.get('/projects/' + project)
    assert r.ok

    # get container w/ ?paths=true
    r = as_public.get('/projects/' + project, params={'paths': 'true'})
    assert r.ok
    assert all('path' in f for f in r.json()['files'])

    # get container w/ ?join=origin&join=origin_job_gear_name
    r = as_public.get('/projects/' + project, params={'join': ['origin', 'origin_job_gear_name']})
    assert r.ok
    assert 'gear_name' in r.json()['join-origin']['job'][job_1]

    # get container w/ ?join_avatars=true
    r = as_public.get('/projects/' + project, params={'join_avatars': 'true'})
    assert r.ok
    assert all('avatar' in perm for perm in r.json()['permissions'])

    # create analyses for testing job inflation
    as_admin.post('/sessions/' + session + '/analyses', files=file_form(
        'analysis.csv', meta={'label': 'no-job', 'inputs': [{'name': 'analysis.csv'}]}))
    as_admin.post('/sessions/' + session + '/analyses', params={'job': 'true'}, json={
        'analysis': {'label': 'with-job'},
        'job': {
            'gear_id': gear,
            'inputs': {
                'csv': {'type': 'project', 'id': project, 'name': 'job_1.csv'}
            }
        }
    })

    # get session and check analyis job inflation
    r = as_admin.get('/sessions/' + session)
    assert r.ok
    assert isinstance(r.json()['analyses'][1]['job'], dict)

    # fail and retry analysis job to test auto-updating on analysis
    analysis_job = r.json()['analyses'][1]['job']['id']
    as_drone.put('/jobs/' + analysis_job, json={'state': 'running'})
    as_drone.put('/jobs/' + analysis_job, json={'state': 'failed'})
    as_drone.post('/jobs/' + analysis_job + '/retry')

    # get session and check analyis job was updated
    r = as_admin.get('/sessions/' + session)
    assert r.ok
    assert r.json()['analyses'][1]['job']['id'] != analysis_job


def test_get_session_jobs(data_builder, default_payload, as_admin, file_form):
    session = data_builder.create_session()
    acquisition = data_builder.create_acquisition()
    gear_doc = default_payload['gear']['gear']
    gear_doc['inputs'] = {
        'dicom': {
            'base': 'file'
        }
    }
    gear = data_builder.create_gear(gear=gear_doc)

    # Add acquisition file
    r = as_admin.post('/acquisitions/' + acquisition + '/files', files=file_form('test.dcm'))
    assert r.ok

    # create an analysis together w/ a job
    r = as_admin.post('/sessions/' + session + '/analyses', params={'job': 'true'}, json={
        'analysis': {'label': 'test analysis'},
        'job': {
            'gear_id': gear,
            'inputs': {
                'dicom': {'type': 'acquisition', 'id': acquisition, 'name': 'test.dcm'}
            }
        }
    })
    assert r.ok

    # get session jobs w/ analysis and job
    r = as_admin.get('/sessions/' + session + '/jobs', params={'join': 'containers'})
    assert r.ok


def test_post_container(data_builder, as_admin, as_user):
    group = data_builder.create_group()

    # create project w/ param inherit=true
    r = as_admin.post('/projects', params={'inherit': 'true'}, json={
        'group': group,
        'label': 'test-inheritance-project'
    })
    assert r.ok
    project = r.json()['_id']

    # set as_user perms to rw on group
    r = as_user.get('/users/self')
    assert r.ok
    uid = r.json()['_id']

    r = as_admin.post('/groups/' + group + '/permissions', json={
        '_id': uid,
        'access': 'rw'
    })
    assert r.ok

    # try to add project without admin on group
    r = as_user.post('/projects', json={
        'group': group,
        'label': 'test project post'
    })
    assert r.status_code == 403

    # set as_user perms to rw on project
    r = as_user.get('/users/self')
    assert r.ok
    uid = r.json()['_id']

    r = as_admin.post('/projects/' + project + '/permissions', json={
        '_id': uid,
        'access': 'rw'
    })
    assert r.ok

    # create session w/ timestamp as rw user
    r = as_user.post('/sessions', json={
        'project': project,
        'label': 'test-timestamp-session',
        'timestamp': '1979-01-01T00:00:00+00:00'
    })
    assert r.ok

    data_builder.delete_group(group, recursive=True)


def test_put_container(data_builder, as_admin):
    session = data_builder.create_session()
    session_2 = data_builder.create_session()

    # test empty update
    r = as_admin.put('/sessions/' + session, json={})
    assert r.status_code == 400

    # update session w/ timestamp
    r = as_admin.put('/sessions/' + session, json={
        'timestamp': '1979-01-01T00:00:00+00:00'
    })
    assert r.ok

    # test that an update to subject.code
    # will create a new subject._id
    r = as_admin.get('/sessions/'+session)
    assert r.ok
    old_subject_id = r.json().get('subject',{}).get('_id')
    r = as_admin.put('/sessions/' + session, json={
        'subject': {
            'code': 'newCode'
        }
    })
    assert r.ok
    r = as_admin.get('/sessions/' + session)
    new_subject_id = r.json().get('subject',{}).get('_id')
    assert new_subject_id != old_subject_id

    # check that an update to subject.First Name
    # will not create a new subject._id
    r = as_admin.get('/sessions/'+session)
    assert r.ok
    old_subject_id = r.json().get('subject',{}).get('_id')
    r = as_admin.put('/sessions/' + session, json={
        'subject': {
            'firstname': 'NewName'
        }
    })
    assert r.ok
    r = as_admin.get('/sessions/' + session)
    new_subject_id = r.json().get('subject',{}).get('_id')
    assert new_subject_id == old_subject_id

    # update session and not the subject
    r = as_admin.put('/sessions/' + session, json={
        'label': 'patience_343'
    })
    assert r.ok

    # update session.subject.code to that of session_2
    # first set session_2.subject.code to something
    r = as_admin.put('/sessions/' + session_2, json={
        'subject': {
            'code': 'subject2'
        }
    })
    assert r.ok
    r = as_admin.get('/sessions/'+session_2)
    assert r.ok
    subject2Id = r.json().get('subject').get('_id')
    r = as_admin.put('/sessions/' + session, json={
        'subject': {
            'code': 'subject2'
        }
    })
    assert r.ok
    r = as_admin.get('/sessions/'+session)
    assert r.ok
    assert r.json().get('subject').get('_id') == subject2Id

    # update subject w/ oid
    r = as_admin.put('/sessions/' + session, json={
        'subject': {'_id': '000000000000000000000000'}
    })
    assert r.ok


def test_subject_age_must_be_int(data_builder, as_admin):
    # Ensure subject age can only be set as int (and None)
    # Found old data that had subject age stored as float

    session = data_builder.create_session()

    subject_age = 123.2

    # Attempt to send age as float
    r = as_admin.put('/sessions/' + session, json={
        'subject': {
            'age': subject_age
        }
    })
    assert r.status_code == 400

    subject_age = 123

    # Ensure subject age set as int works correctly
    r = as_admin.put('/sessions/' + session, json={
        'subject': {
            'age': subject_age
        }
    })
    assert r.ok

    r = as_admin.get('/sessions/' + session)
    assert subject_age == r.json()['subject']['age']

def test_subject_no_name_hashes(data_builder, as_admin):
    # Test that subjects no longer take first and lastname hashes
    session = data_builder.create_session()
    r = as_admin.get('/sessions/' + session)
    assert r.ok
    assert not r.json().get('firstname_hash')
    assert not r.json().get('lastname_hash')

    r = as_admin.put('/sessions/' + session, json={
        'subject': {
            'firstname_hash': 'hash',
            'lastname_hash': 'hash_2'
        }
    })
    assert r.status_code == 400

def test_analysis_put(data_builder, default_payload, as_admin, file_form):
    project = data_builder.create_project()
    session = data_builder.create_session()
    gear_doc = default_payload['gear']['gear']
    gear_doc['inputs'] = {
        'csv': {
            'base': 'file'
        }
    }
    gear = data_builder.create_gear(gear=gear_doc)

    # Add project file
    r = as_admin.post('/projects/' + project + '/files', files=file_form('job_1.csv'))
    assert r.ok

    # add session analysis
    r = as_admin.post('/sessions/' + session + '/analyses', params={'job': 'true'}, json={
        'analysis': {'label': 'with-job'},
        'job': {
            'gear_id': gear,
            'inputs': {
                'csv': {'type': 'project', 'id': project, 'name': 'job_1.csv'}
            }
        }
    })

    assert r.ok
    analysis = r.json()['_id']
    r = as_admin.put('/sessions/'+session + '/analyses/' + analysis, json={'label': 'ayo'})
    assert r.ok
    r = as_admin.get('/sessions/'+session + '/analyses/' + analysis)
    assert r.ok
    assert r.json()['label'] == 'ayo'

    r = as_admin.put('/sessions/'+session + '/analyses/' + analysis, json={'input': 'ayo'})
    assert r.status_code == 400

    r = as_admin.put('/sessions/'+session + '/analyses/' + analysis, json={})
    assert r.status_code == 400

    r = as_admin.put('/sessions/'+session + '/analyses/' + analysis)
    assert r.status_code == 400

def test_edit_file_attributes(data_builder, as_admin, file_form):
    project = data_builder.create_project()
    file_name = 'test_file.txt'

    assert as_admin.post('/projects/' + project + '/files', files=file_form(file_name)).ok

    payload = {
        'type': 'new type',
        'modality': 'new modality',
        'measurements': ['measurement']
    }

    assert as_admin.put('/projects/' + project + '/files/' + file_name, json=payload).ok

    r = as_admin.get('/projects/' + project + '/files/' + file_name + '/info')
    assert r.ok

    file_object = r.json()
    assert file_object['type'] == payload['type']
    assert file_object['measurements'] == payload['measurements']
    assert file_object['modality'] == payload['modality']


    # Attempt to set forbidden fields
    payload = {
        'name': 'new_file_name.txt'
    }
    r = as_admin.put('/projects/' + project + '/files/' + file_name, json=payload)
    assert r.status_code == 400

    # Attempt to update with empty payload
    payload = {}
    r =as_admin.put('/projects/' + project + '/files/' + file_name, json=payload)
    assert r.status_code == 400

    payload = {
        'info': {}
    }
    r = as_admin.put('/projects/' + project + '/files/' + file_name, json=payload)
    assert r.status_code == 400

    payload = {
        'mimetype': 'bad data'
    }
    r = as_admin.put('/projects/' + project + '/files/' + file_name, json=payload)
    assert r.status_code == 400


def test_edit_file_info(data_builder, as_admin, file_form):
    project = data_builder.create_project()
    file_name = 'test_file.txt'

    r = as_admin.post('/projects/' + project + '/files', files=file_form(file_name))
    assert r.ok

    r = as_admin.get('/projects/' + project + '/files/' + file_name + '/info')
    assert r.ok
    assert r.json()['info'] == {}

    # Send improper payload
    r = as_admin.post('/projects/' + project + '/files/' + file_name + '/info', json={
        'delete': ['map'],
        'replace': {'not_going': 'to_happen'}
    })
    assert r.status_code == 400

    # Send improper payload
    r = as_admin.post('/projects/' + project + '/files/' + file_name + '/info', json={
        'delete': {'a': 'map'},
    })
    assert r.status_code == 400

    # Send improper payload
    r = as_admin.post('/projects/' + project + '/files/' + file_name + '/info', json={
        'set': 'cannot do this',
    })
    assert r.status_code == 400

    # Attempt full replace of info
    file_info = {
        'a': 'b',
        'test': 123,
        'map': {
            'a': 'b'
        },
        'list': [1,2,3]
    }


    r = as_admin.post('/projects/' + project + '/files/' + file_name + '/info', json={
        'replace': file_info
    })
    assert r.ok

    r = as_admin.get('/projects/' + project + '/files/' + file_name + '/info')
    assert r.ok
    assert r.json()['info'] == file_info


    # Use 'set' to add new key
    r = as_admin.post('/projects/' + project + '/files/' + file_name + '/info', json={
        'set': {'map': 'no longer a map'}
    })
    assert r.ok

    file_info['map'] = 'no longer a map'
    r = as_admin.get('/projects/' + project + '/files/' + file_name + '/info')
    assert r.ok
    assert r.json()['info'] == file_info


    # Use 'set' to do full replace of "map" key
    r = as_admin.post('/projects/' + project + '/files/' + file_name + '/info', json={
        'set': {'map': 'no longer a map'}
    })
    assert r.ok

    file_info['map'] = 'no longer a map'
    r = as_admin.get('/projects/' + project + '/files/' + file_name + '/info')
    assert r.ok
    assert r.json()['info'] == file_info


    # Use 'delete' to unset "map" key
    r = as_admin.post('/projects/' + project + '/files/' + file_name + '/info', json={
        'delete': ['map', 'a']
    })
    assert r.ok

    file_info.pop('map')
    file_info.pop('a')
    r = as_admin.get('/projects/' + project + '/files/' + file_name + '/info')
    assert r.ok
    assert r.json()['info'] == file_info


    # Use 'delete' on keys that do not exist
    r = as_admin.post('/projects/' + project + '/files/' + file_name + '/info', json={
        'delete': ['madeup', 'keys']
    })
    assert r.ok

    r = as_admin.get('/projects/' + project + '/files/' + file_name + '/info')
    assert r.ok
    assert r.json()['info'] == file_info


    # Use 'replace' to set file info to {}
    r = as_admin.post('/projects/' + project + '/files/' + file_name + '/info', json={
        'replace': {}
    })
    assert r.ok

    r = as_admin.get('/projects/' + project + '/files/' + file_name + '/info')
    assert r.ok
    assert r.json()['info'] == {}








