def test_collections(data_builder, as_admin):
    session = data_builder.create_session()
    acquisition = data_builder.create_acquisition()

    # create collection
    r = as_admin.post('/collections', json={
        'label': 'SciTran/Testing',
        'public': True
    })
    assert r.ok
    collection = r.json()['_id']

    # get all collections w/ stats=true
    r = as_admin.get('/collections', params={'stats': 'true'})
    assert r.ok
    assert all('session_count' in coll for coll in r.json())

    # get collection
    r = as_admin.get('/collections/' + collection)
    assert r.ok

    # test empty update
    r = as_admin.put('/collections/' + collection, json={})
    assert r.status_code == 400

    # add session to collection
    r = as_admin.put('/collections/' + collection, json={
        'contents': {
            'operation': 'add',
            'nodes': [
                {'level': 'session', '_id': session}
            ],
        }
    })
    assert r.ok

    # test if collection is listed at acquisition
    r = as_admin.get('/acquisitions/' + acquisition)
    assert r.ok
    assert collection in r.json()['collections']

    # delete collection
    r = as_admin.delete('/collections/' + collection)
    assert r.ok

    # try to get deleted collection
    r = as_admin.get('/collections/' + collection)
    assert r.status_code == 404

    # test if collection is listed at acquisition
    r = as_admin.get('/acquisitions/' + acquisition)
    assert collection not in r.json()['collections']

def test_collections_phi(data_builder, as_admin, as_user, log_db, file_form):
    session = data_builder.create_session()
    acquisition = data_builder.create_acquisition()

    # create collection
    r = as_admin.post('/collections', json={
        'label': 'SciTran/Testing',
        'public': True
    })
    assert r.ok
    collection = r.json()['_id']

    file_name = 'test_file.txt'

    assert as_admin.post('/collections/' + collection + '/files', files=file_form(file_name)).ok

    # Attempt full replace of info
    file_info = {
        'a': 'b',
        'test': 123,
        'map': {
            'a': 'b'
        },
        'list': [1,2,3]
    }


    r = as_admin.post('/collections/' + collection + '/files/' + file_name + '/info', json={
        'replace': file_info
    })
    assert r.ok


    # Test phi access for list returns with phi access level
    pre_log = log_db.access_log.count({})
    r = as_admin.get('/collections', params={"phi":False})
    assert r.ok
    for collection_ in r.json():
        assert collection_.get('files',[{}])[0].get('info') == None
    assert pre_log == log_db.access_log.count({})
    r = as_admin.get('/collections', params={'phi':True})
    assert r.ok
    for collection_ in r.json():
        print collection_
        assert collection_.get('files',[{}])[0].get('info').get('a') == "b"
    assert pre_log == log_db.access_log.count({}) - len(r.json())

    # Test phi access for individual elements with phi access level
    pre_log = log_db.access_log.count({})
    r = as_admin.get('/collections/' + collection)
    assert r.ok
    assert r.json().get('files',[{}])[0].get('info').get('a') == "b"
    assert pre_log == log_db.access_log.count({}) - 1
    pre_log = log_db.access_log.count({})

    r = as_admin.get('/collections/' + collection, params={'phi':True})
    assert r.ok
    assert r.json().get('files',[{}])[0].get('info').get('a') == "b"
    assert pre_log == log_db.access_log.count({}) - 1
