import time

def test_batch(data_builder, as_user, as_admin, as_root):
    gear = data_builder.create_gear()
    analysis_gear = data_builder.create_gear(category='analysis')
    invalid_gear = data_builder.create_gear(gear={'custom': {'flywheel': {'invalid': True}}})

    empty_project = data_builder.create_project()
    project = data_builder.create_project()
    session = data_builder.create_session(project=project)
    acquisition = data_builder.create_acquisition(session=session)
    as_admin.post('/acquisitions/' + acquisition + '/files', files={
        'file': ('test.txt', 'test\ncontent\n')})

    # get all
    r = as_user.get('/batch')
    assert r.ok

    # get all w/o enforcing permissions
    r = as_admin.get('/batch')
    assert r.ok

    # get all as root
    r = as_root.get('/batch')
    assert r.ok

    # try to create batch without gear_id/targets
    r = as_admin.post('/batch', json={})
    assert r.status_code == 400

    # try to create batch with different target container types
    r = as_admin.post('/batch', json={
        'gear_id': gear,
        'targets': [
            {'type': 'session', 'id': 'test-session-id'},
            {'type': 'acquisition', 'id': 'test-acquisition-id'},
        ],
    })
    assert r.status_code == 400

    # try to create batch using an invalid gear
    r = as_admin.post('/batch', json={
        'gear_id': invalid_gear,
        'targets': [{'type': 'session', 'id': 'test-session-id'}],
    })
    assert r.status_code == 400

    # try to create batch for project w/o acquisitions
    r = as_admin.post('/batch', json={
        'gear_id': gear,
        'targets': [{'type': 'project', 'id': empty_project}]
    })
    assert r.status_code == 404

    # try to create batch w/o write permission
    r = as_user.post('/batch', json={
        'gear_id': gear,
        'targets': [{'type': 'project', 'id': project}]
    })
    assert r.status_code == 403

    # create a batch w/ session target
    r = as_admin.post('/batch', json={
        'gear_id': gear,
        'targets': [{'type': 'session', 'id': session}]
    })
    assert r.ok

    # create a batch w/ acquisition target and target_context
    r = as_admin.post('/batch', json={
        'gear_id': gear,
        'targets': [{'type': 'acquisition', 'id': acquisition}],
        'target_context': {'type': 'session', 'id': session}
    })
    assert r.ok
    batch_id = r.json()['_id']

    # create a batch w/ analysis gear
    r = as_admin.post('/batch', json={
        'gear_id': analysis_gear,
        'targets': [{'type': 'session', 'id': session}]
    })
    assert r.ok
    analysis_batch_id = r.json()['_id']

    # try to get non-existent batch
    r = as_admin.get('/batch/000000000000000000000000')
    assert r.status_code == 404

    # try to get batch w/o perms (different user)
    r = as_user.get('/batch/' + batch_id)
    assert r.status_code == 403

    # get batch
    r = as_admin.get('/batch/' + batch_id)
    assert r.ok
    assert r.json()['state'] == 'pending'

    # get batch w/ ?jobs=true
    r = as_admin.get('/batch/' + batch_id, params={'jobs': 'true'})
    assert r.ok
    assert 'jobs' in r.json()

    # try to cancel non-running batch
    r = as_admin.post('/batch/' + batch_id + '/cancel')
    assert r.status_code == 400

    # run batch
    r = as_admin.post('/batch/' + batch_id + '/run')
    assert r.ok

    # test batch.state after calling run
    r = as_admin.get('/batch/' + batch_id)
    assert r.json()['state'] == 'running'

    # try to run non-pending batch
    r = as_admin.post('/batch/' + batch_id + '/run')
    assert r.status_code == 400

    # cancel batch
    r = as_admin.post('/batch/' + batch_id + '/cancel')
    assert r.ok

    # test batch.state after calling cancel
    r = as_admin.get('/batch/' + batch_id)
    assert r.json()['state'] == 'cancelled'

    # run analysis batch
    r = as_admin.post('/batch/' + analysis_batch_id + '/run')
    assert r.ok

    # test batch.state after calling run
    r = as_admin.get('/batch/' + analysis_batch_id)
    assert r.json()['state'] == 'running'


    # Test batch complete
    # create a batch w/ acquisition target and target_context
    r = as_admin.post('/batch', json={
        'gear_id': gear,
        'targets': [{'type': 'acquisition', 'id': acquisition}],
        'target_context': {'type': 'session', 'id': session}
    })
    assert r.ok
    batch_id = r.json()['_id']

    # run batch
    r = as_admin.post('/batch/' + batch_id + '/run')
    assert r.ok

    # test batch.state after calling run
    r = as_admin.get('/batch/' + batch_id)
    assert r.json()['state'] == 'running'

    for job in r.json()['jobs']:
        # set jobs to complete
        r = as_root.put('/jobs/' + job, json={'state': 'running'})
        assert r.ok
        r = as_root.put('/jobs/' + job, json={'state': 'complete'})
        assert r.ok

    # test batch is complete
    r = as_admin.get('/batch/' + batch_id)
    assert r.json()['state'] == 'complete'

    # Test batch failed with acquisition target
    # create a batch w/ acquisition target and target_context
    r = as_admin.post('/batch', json={
        'gear_id': gear,
        'targets': [{'type': 'acquisition', 'id': acquisition}],
        'target_context': {'type': 'session', 'id': session}
    })
    assert r.ok
    batch_id = r.json()['_id']

    # run batch
    r = as_admin.post('/batch/' + batch_id + '/run')
    assert r.ok

    # test batch.state after calling run
    r = as_admin.get('/batch/' + batch_id)
    assert r.json()['state'] == 'running'

    for job in r.json()['jobs']:
        # set jobs to failed
        r = as_root.put('/jobs/' + job, json={'state': 'running'})
        assert r.ok
        r = as_root.put('/jobs/' + job, json={'state': 'failed'})
        assert r.ok

    # test batch is complete
    r = as_admin.get('/batch/' + batch_id)
    assert r.json()['state'] == 'failed'

    # Test batch complete with analysis target
    # create a batch w/ analysis gear
    r = as_admin.post('/batch', json={
        'gear_id': analysis_gear,
        'targets': [{'type': 'session', 'id': session}]
    })
    assert r.ok
    batch_id = r.json()['_id']

    # run batch
    r = as_admin.post('/batch/' + batch_id + '/run')
    assert r.ok

    # test batch.state after calling run
    r = as_admin.get('/batch/' + batch_id)
    assert r.json()['state'] == 'running'

    for job in r.json()['jobs']:
        # set jobs to complete
        r = as_root.put('/jobs/' + job, json={'state': 'running'})
        assert r.ok
        r = as_root.put('/jobs/' + job, json={'state': 'complete'})
        assert r.ok

    # test batch is complete
    r = as_admin.get('/batch/' + batch_id)
    assert r.json()['state'] == 'complete'

    # Test batch failed with analysis target
    # create a batch w/ analysis gear
    r = as_admin.post('/batch', json={
        'gear_id': analysis_gear,
        'targets': [{'type': 'session', 'id': session}]
    })
    assert r.ok
    batch_id = r.json()['_id']

    # run batch
    r = as_admin.post('/batch/' + batch_id + '/run')
    assert r.ok

    # test batch.state after calling run
    r = as_admin.get('/batch/' + batch_id)
    assert r.json()['state'] == 'running'

    for job in r.json()['jobs']:
        # set jobs to failed
        r = as_root.put('/jobs/' + job, json={'state': 'running'})
        r = as_root.put('/jobs/' + job, json={'state': 'failed'})
        assert r.ok

    # test batch is complete
    r = as_admin.get('/batch/' + batch_id)
    assert r.json()['state'] == 'failed'

def test_no_input_batch(data_builder, as_admin, as_root):
    project = data_builder.create_project()
    session = data_builder.create_session(project=project)
    acquisition = data_builder.create_acquisition(session=session)

    gear_doc = default_payload['gear']['gear']
    gear_doc['inputs'] = {
        'api_key': {
            'base': 'api-key'
        }
    }
    gear = data_builder.create_gear(gear=gear_doc)

    # create a batch w/o inputs targeting session
    r = as_admin.post('/batch', json={
        'gear_id': gear,
        'targets': [{'type': 'session', 'id': session}]
    })
    assert r.ok
    batch1 = r.json()
    assert len(batch1['matched']) == 1
    assert batch1['matched'][0]['id'] == session

    # create a batch w/o inputs targeting acquisition
    r = as_admin.post('/batch', json={
        'gear_id': gear,
        'targets': [{'type': 'acquisition', 'id': acquisition}]
    })
    assert r.ok
    batch2 = r.json()
    assert len(batch2['matched']) == 1
    assert batch2['matched'][0]['id'] == session

    # create a batch w/o inputs targeting project
    r = as_admin.post('/batch', json={
        'gear_id': gear,
        'targets': [{'type': 'project', 'id': project}]
    })
    assert r.ok
    batch3 = r.json()
    assert len(batch3['matched']) == 1
    assert batch3['matched'][0]['id'] == session

    batch_id = batch1['_id']

    # run batch
    r = as_admin.post('/batch/' + batch_id['_id'] + '/run')
    assert r.ok

    # test batch.state after calling run
    r = as_admin.get('/batch/' + batch_id)
    assert r.json()['state'] == 'running'

    for job in r.json()['jobs']:
        # set jobs to failed
        r = as_root.put('/jobs/' + job, json={'state': 'running'})
        assert r.ok
        r = as_root.put('/jobs/' + job, json={'state': 'complete'})
        assert r.ok

    # test batch is complete
    r = as_admin.get('/batch/' + batch_id)
    assert r.json()['state'] == 'complete'
