"""
The main server of HistomicsML

Input: training samples (json)
Output: prediction results in the form of RedisDB
"""
import os
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '1'
import json
import h5py
import numpy as np
import redis
import cv2
import large_image
import mysql.connector

from copy import copy
from time import time
import imageio
from sklearn.externals import joblib
#import joblib

# inner functions
import init
import settings
import networks
import view
import heatmap
import dataset
import users
import train
import retrainView
import retrainHeatmap
import augments
import selectonly
import save
import label
import count
import mapping
import picker
import validate

# import cython functions
from loadPredictswithCenXY import load
from getItemIndex import getIdx

# initialize all settings
set = settings.Settings()

try:
    # connect to Redis server
    db = redis.StrictRedis(host=set.REDIS_HOST,
                           port=set.REDIS_PORT, db=set.REDIS_DB)
    print(db)
    print(db.ping())
    print('Connected!')
except Exception as ex:
    print('Error:', ex)
    exit('Failed to connect, terminating.')

def run():
    # initialize VGG Model and PCA
    iset = init.Init()
    # initialize neural network model
    model = networks.Network()
    model.init_model()
    # initialize global instance
    uset = users.Users()
    init_picker = picker.picker()

    # store special features in memory
    # dset_special = dataset.Dataset(set.PATH_TO_SPECIAL)
    dset_special = None
    # set normal features in memory to false
    is_normal_loaded = True
    tset_name = None
    is_reloaded = False
    m_checkpoints = 0
    print("Dataset Loaded.")

    while True:
        queue = db.lrange(set.REQUEST_QUEUE, set.REQUEST_START, set.REQUEST_END)
        q_uid = None
        # initialize local instance
        select = selectonly.Select()
        finalize = save.Save()
        viewer = view.View()
        retrain_v = retrainView.retrainView()
        retrain_h = retrainHeatmap.retrainHeatmap()
        heat = heatmap.Heatmap()
        t_train = train.Train()
        report_label = label.label()
        report_count = count.count()
        report_map = mapping.map()
        report_validate = validate.validate()
        for q in queue:
            q = json.loads(q.decode("utf-8"))
            q_uid = q["uid"]
            target = q["target"]
            session_uid = q["uid"]
            dataSetPath = set.DATASET_DIR + q["dataset"]
            pcaPath = set.DATASET_DIR + q["pca"]
            # if specific features then set m_loaded to true
            is_normal_loaded = False if dataSetPath == set.PATH_TO_SPECIAL else True

            if target == "label":
                report_label.setData(q)

            if target == "params":
                model.params_setting(q)

            if target == "count":
                report_count.setData(q)

            if target == "map":
                report_map.setData(q)

            if target == 'selectonly':
                select.setData(q)

            if target == 'save':
                finalize.setData(q)

            if target == 'view':
                viewer.setData(q)

            if target == 'retrainView':
                retrain_v.setData(q)

            if target == 'retrainHeatmap':
                retrain_h.setData(q)

            if target == 'heatmapAll':
                heatmaps = q["viewJSONs"]

            if target == 'heatmap':
                heat.setData(q)

            if target == 'train':
                t_train.setData(q)

            if target == 'reload':
                t_path = set.TRAININGSET_DIR + q["trainingSetName"]
                m_path = set.MODEL_DIR + q["trainingSetName"]
                is_reloaded = True

            if target == 'reviewSave':
                q_samples = json.loads(q["samples"])

            if target == 'initpicker':
                init_picker.setData(q)

            if target == 'addpicker':
                init_picker.addData(q)

            if target == 'validate':
                report_validate.setData(q)

            if target == 'updatepicker':
                q_samples = json.loads(q["samples"])

        if q_uid is not None:

            print(target, " Session Start .....")

            no_uid = True
            uidx = 0

            # find current user Index
            for i in range(len(uset.users)):
                if uset.users[i]['uid'] == session_uid:
                    uidx = i
                    no_uid = False

            if no_uid:
                # set users data
                uset.addUser(session_uid)

            if is_normal_loaded:
                dset = dataset.Dataset(dataSetPath)
            else:
                dset = dataset.Dataset(set.PATH_TO_SPECIAL)

            if target == 'selectonly':
                uset.setIter(uidx, select.iter)
                print("Predict Start ... ")
                t0 = time()
                scores = model.predict_prob(dset.features)
                t1 = time()
                print("Predict took ", t1 - t0)
                # Find uncertain samples
                data = select.getData(scores, dset.slideIdx, dset.slides, dset.x_centroid, dset.y_centroid)
                db.set(q_uid, json.dumps(data))
                db.ltrim(set.REQUEST_QUEUE, len(q_uid), -1)

            if target == 'view':
                slide_idx = dset.getSlideIdx(viewer.slide)
                object_num = dset.getObjNum(slide_idx)
                data_idx = dset.getDataIdx(slide_idx)
                feature_set = dset.getFeatureSet(data_idx, object_num)
                x_centroid_set = dset.getXcentroidSet(data_idx, object_num)
                y_centroid_set = dset.getYcentroidSet(data_idx, object_num)

                print("Predict Start ... ")
                t0 = time()
                predictions = model.predict(feature_set)
                t1 = time()
                print("Predict took ", t1 - t0)
                object_idx = load(
                    viewer.left, viewer.right, viewer.top, viewer.bottom, x_centroid_set.astype(np.float), y_centroid_set.astype(np.float)
                )
                data = {}

                for i in object_idx:
                    data[str(x_centroid_set[i][0])+'_'+str(y_centroid_set[i][0])] = str(predictions[i])

                db.set(q_uid, json.dumps(data))
                db.ltrim(set.REQUEST_QUEUE, len(q_uid), -1)

            if target == 'heatmap':
                slide_idx = dset.getSlideIdx(heat.slide)
                object_num = dset.getObjNum(slide_idx)
                data_idx = dset.getDataIdx(slide_idx)
                feature_set = dset.getFeatureSet(data_idx, object_num)
                x_centroid_set = dset.getXcentroidSet(data_idx, object_num)
                y_centroid_set = dset.getYcentroidSet(data_idx, object_num)

                print("Predict Start ... ")
                t0 = time()
                if set.IS_HEATMAP == False:
                    scores = model.predict_prob(feature_set)
                t1 = time()
                print("Predict took ", t1 - t0)
                # set x and y maps
                heat.setXandYmap()
                # write heatmaps
                heat.setHeatMap(x_centroid_set, y_centroid_set, scores)
                # get heatmap data
                data = heat.getData(0)

                print(data)
                db.set(q_uid, json.dumps(data))
                db.ltrim(set.REQUEST_QUEUE, len(q_uid), -1)

            if target == 'heatmapAll':
                data = []
                index = 0

                t0 = time()
                scores = model.predict_prob(dset.features)
                t1 = time()
                print("Predict took ", t1 - t0)

                for h in heatmaps:

                    h['uid'] = session_uid
                    heat.setData(h)

                    slide_idx = dset.getSlideIdx(heat.slide)
                    object_num = dset.getObjNum(slide_idx)
                    data_idx = dset.getDataIdx(slide_idx)
                    # feature_set = dset.getFeatureSet(data_idx, object_num)
                    x_centroid_set = dset.getXcentroidSet(data_idx, object_num)
                    y_centroid_set = dset.getYcentroidSet(data_idx, object_num)
                    score_set = scores[data_idx: data_idx+object_num]
                    # set x and y maps
                    heat.setXandYmap()
                    # write heatmaps
                    heat.setHeatMap(x_centroid_set, y_centroid_set, score_set)
                    # get heatmap data
                    data_k = heat.getData(index)
                    data.append(data_k)
                    index += 1

                # print data
                db.set(q_uid, json.dumps(data))
                db.ltrim(set.REQUEST_QUEUE, len(q_uid), -1)

            if target == 'reload':
                # initialize augment
                agen = augments.Augments()
                # set user train samples
                # uset.setReloadedData(uidx, t_path, dset.slides)
                uset.setReloadedData(uidx, t_path)

                sample_size = len(uset.users[uidx]['samples'])

                m_checkpoints = uset.users[uidx]['samples'][sample_size-1]['checkpoints']

                sample_batch_size = agen.AUG_BATCH_SIZE * sample_size
                train_size = sample_size + sample_batch_size

                train_features = np.zeros((train_size, set.FEATURE_DIM))
                train_labels = np.zeros((train_size, ))

                for i in range(sample_size):
                    train_features[i] = uset.users[uidx]['samples'][i]['feature']
                    train_labels[i] = uset.users[uidx]['samples'][i]['label']
                    train_features[i+sample_size:i+sample_size+agen.AUG_BATCH_SIZE] = uset.users[uidx]['augments'][i]['feature']
                    train_labels[i+sample_size:i+sample_size+agen.AUG_BATCH_SIZE] = uset.users[uidx]['augments'][i]['label']

                tset_path = t_path.split('/')[-1]
                tset_name = tset_path.split('.')[0]

                model.loading_model(m_path)

                model.setParams(uset.params_list)

                print("Training ... ", len(train_labels))
                t0 = time()
                model.train_model(train_features, train_labels, tset_name)
                t1 = time()
                print("Training took ", t1 - t0)

                # data = {"success": 'pass'}
                data = {}
                data['parameters'] = []
                for params in uset.params_list:
                    data['parameters'].append(params)

                db.set(q_uid, json.dumps(data))
                db.ltrim(set.REQUEST_QUEUE, len(q_uid), -1)

            if target == 'label':
                # initialize augment
                agen = augments.Augments()
                # set user train samples
                uset.setReloadedData(uidx, report_label.trainSet)

                sample_size = len(uset.users[uidx]['samples'])
                sample_batch_size = agen.AUG_BATCH_SIZE * sample_size
                train_size = sample_size + sample_batch_size

                train_features = np.zeros((train_size, set.FEATURE_DIM))
                train_labels = np.zeros((train_size, ))

                for i in range(sample_size):
                    train_features[i] = uset.users[uidx]['samples'][i]['feature']
                    train_labels[i] = uset.users[uidx]['samples'][i]['label']
                    train_features[i+sample_size:i+sample_size+agen.AUG_BATCH_SIZE] = uset.users[uidx]['augments'][i]['feature']
                    train_labels[i+sample_size:i+sample_size+agen.AUG_BATCH_SIZE] = uset.users[uidx]['augments'][i]['label']

                print("Training ... ", len(train_labels))
                t0 = time()
                model.train_model(train_features, train_labels, report_label.classifier)
                t1 = time()
                print("Training took ", t1 - t0)

                slide_idx = dset.getSlideIdx(report_label.slide)
                object_num = dset.getObjNum(slide_idx)
                data_idx = dset.getDataIdx(slide_idx)
                test_features = dset.getFeatureSet(data_idx, object_num)
                x_centroid_set = dset.getXcentroidSet(data_idx, object_num)
                y_centroid_set = dset.getYcentroidSet(data_idx, object_num)
                print("Testing Start ... ")
                t0 = time()
                predicts = model.predict(test_features)
                t1 = time()
                print("Predict took ", t1 - t0)

                masterDirectory = '/'+dataSetPath.split('/')[1]
                dataDirectory = '/'+dataSetPath.split('/')[2]

                inputImageFile = masterDirectory+dataDirectory+'/tif/'+ report_label.slide + '.svs.dzi.tif'

                bold = 512
                bold_left = report_label.left - bold
                bold_top = report_label.top - bold
                bold_bottom = report_label.bottom + bold
                bold_right = report_label.right + bold
                bold_width = report_label.width + 2*bold
                bold_height = report_label.height + 2*bold

                ts = large_image.getTileSource(inputImageFile)

                region = dict(
                    left=report_label.left, top=report_label.top,
                    width=report_label.width, height=report_label.height,
                )

                im_region = ts.getRegion(
                    region=region, format=large_image.tilesource.TILE_FORMAT_NUMPY
                )[0]

                mydb = mysql.connector.connect(
                  host=set.MYSQL_HOST,
                  user="guest",
                  passwd="guest",
                  database="nuclei",
                  charset='utf8',
                  use_unicode=True
                )

                boundaryTablename = 'sregionboundaries'

                runcursor = mydb.cursor()

                query = 'SELECT centroid_x, centroid_y, boundary from ' + boundaryTablename + ' where slide="' +  report_label.slide + \
                '" AND centroid_x BETWEEN ' + str(bold_left) + ' AND ' + str(bold_right) + \
                ' AND centroid_y BETWEEN ' + str(bold_top) + ' AND ' + str(bold_bottom)

                runcursor.execute(query)

                boundarySet = runcursor.fetchall()

                # find region index from hdf5
                object_idx = load(
                    bold_left, bold_right, bold_top, bold_bottom, x_centroid_set.astype(np.float), y_centroid_set.astype(np.float)
                )

                # set an array for boundary points in a region to zero
                im_bold = np.zeros((bold_height, bold_width), dtype=np.uint8)

                for i in object_idx:
                    for j in range(len(boundarySet)):
                      x = int(boundarySet[j][0])
                      y = int(boundarySet[j][1])
                      boundaryPoints = []
                      if x == int(x_centroid_set[i, 0]) and y == int(y_centroid_set[i, 0]):
                          object = boundarySet[j][2].encode('utf-8').split(' ')
                          object_points = []
                          for p in range(len(object)-1):
                              intP = map(int, object[p].split(','))
                              intP[0] = intP[0] - report_label.left + bold
                              intP[1] = intP[1] - report_label.top + bold
                              object_points.append(intP)
                          boundaryPoints.append(np.asarray(object_points))
                          cv2.fillPoly(im_bold, boundaryPoints, 255 if predicts[i] > 0 else 128)

                im_out = im_bold[bold:bold+report_label.height, bold:bold+report_label.width]

                # imsave(report_label.inFile, im_out)
                imageio.imwrite(report_label.inFile, im_out)

                runcursor.close()
                mydb.close()

                print ("label success ", report_label.inFile)
                data = {"success": report_label.outFile}
                db.set(q_uid, json.dumps(data))
                db.ltrim(set.REQUEST_QUEUE, len(q_uid), -1)

                uset.users = []
                uset.u_size = 0

                model = networks.Network()
                model.init_model()
                print ("label done")

            if target == 'count':
                # initialize augment
                agen = augments.Augments()
                # set user train samples
                uset.setReloadedData(uidx, report_count.trainSet)

                sample_size = len(uset.users[uidx]['samples'])
                sample_batch_size = agen.AUG_BATCH_SIZE * sample_size
                train_size = sample_size + sample_batch_size

                train_features = np.zeros((train_size, set.FEATURE_DIM))
                train_labels = np.zeros((train_size, ))

                for i in range(sample_size):
                    train_features[i] = uset.users[uidx]['samples'][i]['feature']
                    train_labels[i] = uset.users[uidx]['samples'][i]['label']
                    train_features[i+sample_size:i+sample_size+agen.AUG_BATCH_SIZE] = uset.users[uidx]['augments'][i]['feature']
                    train_labels[i+sample_size:i+sample_size+agen.AUG_BATCH_SIZE] = uset.users[uidx]['augments'][i]['label']

                print("Training ... ", len(train_labels))
                t0 = time()
                model.train_model(train_features, train_labels, report_count.classifier)
                t1 = time()
                print("Training took ", t1 - t0)

                print("Testing Start ... ")
                t0 = time()
                predicts = model.predict(dset.features)
                t1 = time()
                print("Predict took ", t1 - t0)

                # find positive and negative numbers for each slide
                pos_num = []
                neg_num = []

                for i in range(dset.n_slides):
                    if i == len(dset.dataIdx) - 1:
                        predict = predicts[dset.dataIdx[i, 0]:]
                    else:
                        predict = predicts[dset.dataIdx[i, 0]: dset.dataIdx[i+1, 0]]
                    pos = len(predict[predict>0])
                    neg = len(predict) - pos
                    pos_num.append(pos)
                    neg_num.append(neg)

                print('>> Writing count file')
                out_file = open(report_count.inFile, 'w')

                out_file.write("Slide\t")
                out_file.write("Predicted positive (superpixels)\t")
                out_file.write("Predicted negative (superpixels)\t")
                out_file.write("\n")

                for i in range(len(dset.slides)):
                    out_file.write("%s\t" % dset.slides[i])
                    out_file.write("%d\t" % pos_num[i])
                    out_file.write("%d\t" % neg_num[i])
                    out_file.write("\n")

                out_file.close()
                print ("count success ", report_count.inFile)
                data = {"success": report_count.outFile}
                db.set(q_uid, json.dumps(data))
                db.ltrim(set.REQUEST_QUEUE, len(q_uid), -1)

                uset.users = []
                uset.u_size = 0

                model = networks.Network()
                model.init_model()
                print ("count done")

            if target == 'validate':

                val_trainset = h5py.File(report_validate.trainSet, 'r')
                val_testset = h5py.File(report_validate.testSet, 'r')

                val_trainset_features = val_trainset['features'][:]
                val_trainset_labels = val_trainset['labels'][:]
                val_trainset_labels = np.reshape(val_trainset_labels, (len(val_trainset_labels), ))
                val_trainset_labels[val_trainset_labels<0] = 0

                val_testset_features = val_testset['features'][:]
                val_testset_labels = val_testset['labels'][:]
                val_testset_labels[val_testset_labels<0] = 0

                print("Training ... ", len(val_trainset_labels))
                t0 = time()
                model.train_model(val_trainset_features, val_trainset_labels, report_validate.classifier)
                t1 = time()
                print("Training took ", t1 - t0)

                print("Testing Start ... ")
                t0 = time()
                y_pred = model.predict(val_testset_features)
                t1 = time()
                print("Predict took ", t1 - t0)

                from sklearn.metrics import accuracy_score, f1_score, recall_score, precision_score
                from sklearn import metrics

                accuracy = accuracy_score(val_testset_labels, y_pred)
                f1 = f1_score(val_testset_labels, y_pred)
                recall = recall_score(val_testset_labels, y_pred)
                precision = precision_score(val_testset_labels, y_pred)

                print('>> Writing count file')
                out_file = open(report_validate.inFile, 'w')

                out_file.write("Accuracy\t")
                out_file.write("F1 score\t")
                out_file.write("Recall\t")
                out_file.write("Precision\t")
                out_file.write("\n")

                out_file.write("%.4f\t" % accuracy)
                out_file.write("%.4f\t" % f1)
                out_file.write("%.4f\t" % recall)
                out_file.write("%.4f\t" % precision)
                out_file.write("\n")

                out_file.close()
                print ("validate success ", report_validate.inFile)
                data = {"success": report_validate.outFile}
                db.set(q_uid, json.dumps(data))
                db.ltrim(set.REQUEST_QUEUE, len(q_uid), -1)

            if target == 'map':
                # initialize augment
                agen = augments.Augments()
                # set user train samples
                uset.setReloadedData(uidx, report_map.trainSet)

                sample_size = len(uset.users[uidx]['samples'])
                sample_batch_size = agen.AUG_BATCH_SIZE * sample_size
                train_size = sample_size + sample_batch_size

                train_features = np.zeros((train_size, set.FEATURE_DIM))
                train_labels = np.zeros((train_size, ))

                for i in range(sample_size):
                    train_features[i] = uset.users[uidx]['samples'][i]['feature']
                    train_labels[i] = uset.users[uidx]['samples'][i]['label']
                    train_features[i+sample_size:i+sample_size+agen.AUG_BATCH_SIZE] = uset.users[uidx]['augments'][i]['feature']
                    train_labels[i+sample_size:i+sample_size+agen.AUG_BATCH_SIZE] = uset.users[uidx]['augments'][i]['label']

                print("Training ... ", len(train_labels))
                t0 = time()
                model.train_model(train_features, train_labels, report_map.classifier)
                t1 = time()
                print("Training took ", t1 - t0)

                slide_idx = dset.getSlideIdx(report_map.slide)
                object_num = dset.getObjNum(slide_idx)
                data_idx = dset.getDataIdx(slide_idx)
                test_features = dset.getFeatureSet(data_idx, object_num)
                x_centroid_set = dset.getXcentroidSet(data_idx, object_num)
                y_centroid_set = dset.getYcentroidSet(data_idx, object_num)

                print("Testing Start ... ")
                t0 = time()
                predicts = model.predict(test_features)
                t1 = time()
                print("Predict took ", t1 - t0)

                output = h5py.File(report_map.inFile, 'w')
                output.create_dataset('features', data=test_features)
                output.create_dataset('predicts', data=predicts)
                output.create_dataset('x_centroid', data=x_centroid_set)
                output.create_dataset('y_centroid', data=y_centroid_set)
                output.create_dataset('slides', data=[report_map.slide])
                output.close()

                print ("map success ", report_map.inFile)
                data = {"success": report_map.outFile}
                db.set(q_uid, json.dumps(data))
                db.ltrim(set.REQUEST_QUEUE, len(q_uid), -1)

                uset.users = []
                uset.u_size = 0

                model = networks.Network()
                model.init_model()
                print ("map done")

            if target == 'save':
                if finalize.reloaded == "true":
                    tag = finalize.uid[-3:]
                    modelName = finalize.classifier + "-" + tag + ".h5"
                else:
                    modelName = finalize.classifier + ".h5"
                model.saving_model(finalize.modeldir+modelName)
                data = finalize.getData(uset.users[uidx], modelName, model.getParams())
                db.set(q_uid, json.dumps(data))
                db.ltrim(set.REQUEST_QUEUE, len(q_uid), -1)

            if target == 'params':
                data = model.getParams()
                db.set(q_uid, json.dumps(data))
                db.ltrim(set.REQUEST_QUEUE, len(q_uid), -1)

            if target == 'review':
                data = {}
                data['review'] = []

                for sample in uset.users[uidx]['samples']:
                    sample_data = {}
                    sample_data['id'] = str(sample['id'])
                    sample_data['label'] = 1 if sample['label'] == 1 else -1
                    sample_data['iteration'] = int(sample['iteration'])
                    sample_data['slide'] = str(sample['slide'])
                    sample_data['centX'] = str(sample['centX'])
                    sample_data['centY'] = str(sample['centY'])
                    sample_data['boundary'] = ""
                    sample_data['maxX'] = 0
                    sample_data['maxY'] = 0

                    data['review'].append(sample_data)

                print(data)
                db.set(q_uid, json.dumps(data))
                db.ltrim(set.REQUEST_QUEUE, len(q_uid), -1)

            if target == 'initpicker':
                data = {}
                data['status'] = "PASS"
                data['count'] = init_picker.getCnt()

                db.set(q_uid, json.dumps(data))
                db.ltrim(set.REQUEST_QUEUE, len(q_uid), -1)

            if target == 'getpicker':
                data = {}
                data['status'] = "PASS"
                data['count'] = init_picker.cnt

                db.set(q_uid, json.dumps(data))
                db.ltrim(set.REQUEST_QUEUE, len(q_uid), -1)

            if target == 'addpicker':
                data = {}
                data['status'] = "PASS"
                data['count'] = init_picker.cnt

                db.set(q_uid, json.dumps(data))
                db.ltrim(set.REQUEST_QUEUE, len(q_uid), -1)

            if target == 'updatepicker':
                data = {}
                data['status'] = "PASS"
                data['count'] = init_picker.cnt
                # init_picker.updateData(q_samples)
                for k in q_samples:
                    index = init_picker.out_db_id.index(k['id'])
                    init_picker.out_labels[index] = k['label']

                db.set(q_uid, json.dumps(data))
                db.ltrim(set.REQUEST_QUEUE, len(q_uid), -1)

            if target == 'genreview':
                data = {}
                data['status'] = "PASS"
                data['picker_review'] = []
                for p in range(len(init_picker.out_slides)):
                    sample_dict = {}
                    sample_dict['slide'] = init_picker.out_slides[p]
                    sample_dict['centX'] = init_picker.out_x_centroid[p]
                    sample_dict['centY'] = init_picker.out_y_centroid[p]
                    sample_dict['label'] = init_picker.out_labels[p]
                    data['picker_review'].append(sample_dict)

                db.set(q_uid, json.dumps(data))
                db.ltrim(set.REQUEST_QUEUE, len(q_uid), -1)

            if target == 'savepicker':
                data = {}
                data['status'] = "PASS"
                data['filename'] = init_picker.fileName

                for p in range(len(init_picker.out_slides)):
                    slide_idx = dset.getSlideIdx(init_picker.out_slides[p])
                    object_num = dset.getObjNum(slide_idx)
                    data_idx = dset.getDataIdx(slide_idx)
                    feature_set = dset.getFeatureSet(data_idx, object_num)
                    x_centroid_set = dset.getXcentroidSet(data_idx, object_num)
                    y_centroid_set = dset.getYcentroidSet(data_idx, object_num)
                    slideIdx_set = dset.getSlideIdxSet(data_idx, object_num)
                    c_idx = getIdx(
                        x_centroid_set.astype(np.float), y_centroid_set.astype(np.float),
                        slideIdx_set.astype(np.int), np.float32(init_picker.out_x_centroid[p]),
                        np.float32(init_picker.out_y_centroid[p]), slide_idx
                    )
                    f_idx = data_idx + c_idx
                    init_picker.addFeature(f_idx, feature_set[c_idx])

                init_picker.save()

                db.set(q_uid, json.dumps(data))
                db.ltrim(set.REQUEST_QUEUE, len(q_uid), -1)

            if target == 'train':
                # increase checkpoint by 1
                m_checkpoints += 1
                # initialize augment
                agen = augments.Augments()
                uset.setIter(uidx, t_train.iter)

                for sample in t_train.samples:
                    # init sample and augment
                    init_sample = dict(
                        id=0, f_idx=0, checkpoints=0,
                        aurl=None, feature=None, label=0,
                        iteration=0, centX=0, centY=0,
                        slideIdx=0, slide=None
                    )
                    init_augment = dict(
                        id=[], checkpoints=[], feature=[], label=[]
                    )

                    # check db_id in users samples
                    remove_idx = []
                    for u in range(len(uset.users[uidx]['samples'])):
                        if uset.users[uidx]['samples'][u]['id'] == sample['id']:
                            remove_idx.append(u)

                    for r in remove_idx:
                        uset.users[uidx]['samples'].pop(r)
                        uset.users[uidx]['augments'].pop(r)

                    # add feature
                    init_sample['id'] = sample['id']
                    init_sample['aurl'] = str(sample['aurl'])
                    init_sample['slide'] = str(sample['slide'])
                    # print(init_sample['slide'])

                    slide_idx = dset.getSlideIdx(init_sample['slide'])
                    object_num = dset.getObjNum(slide_idx)
                    data_idx = dset.getDataIdx(slide_idx)
                    feature_set = dset.getFeatureSet(data_idx, object_num)
                    x_centroid_set = dset.getXcentroidSet(data_idx, object_num)
                    y_centroid_set = dset.getYcentroidSet(data_idx, object_num)
                    slideIdx_set = dset.getSlideIdxSet(data_idx, object_num)

                    # print(slide_idx, object_num, data_idx, feature_set, x_centroid_set, slideIdx_set)
                    c_idx = getIdx(
                        x_centroid_set.astype(np.double), y_centroid_set.astype(np.double), slideIdx_set.astype(np.int), np.double(sample['centX']), np.double(sample['centY']), slide_idx
                    )
                    # print(c_idx)

                    f_idx = data_idx + c_idx

                    PCA = joblib.load(pcaPath)

                    init_sample['f_idx'] =  f_idx
                    init_sample['feature'] = feature_set[c_idx]
                    init_sample['label'] = 1 if sample['label'] == 1 else 0
                    init_sample['iteration'] = t_train.iter
                    init_sample['centX'] = sample['centX']
                    init_sample['centY'] = sample['centY']
                    init_sample['checkpoints'] = m_checkpoints

                    # add augment features
                    slide_idx = dset.getSlideIdx(init_sample['slide'])
                    slide_mean = dset.getWSI_Mean(slide_idx)
                    slide_std = dset.getWSI_Std(slide_idx)

                    a_imgs = agen.prepare_image(init_sample['aurl'], slide_mean, slide_std)
                    a_featureSet = iset.FC1_MODEL.predict(a_imgs)
                    a_featureSet = PCA.transform(a_featureSet)
                    a_labelSet = np.zeros((agen.AUG_BATCH_SIZE, )).astype(np.uint8)
                    a_idSet = []
                    a_checkpointSet = []
                    for i in range(agen.AUG_BATCH_SIZE):
                        a_idSet.append(init_sample['id'])
                        a_checkpointSet.append(init_sample['checkpoints'])
                    if init_sample['label'] > 0:
                        a_labelSet.fill(1)

                    init_augment['id'] = a_idSet
                    init_augment['feature'] = a_featureSet
                    init_augment['label'] = a_labelSet
                    init_augment['checkpoints'] = a_checkpointSet

                    uset.setAugmentData(uidx, init_augment)
                    uset.setTrainSampleData(uidx, init_sample)

                sample_size = len(uset.users[uidx]['samples'])
                sample_batch_size = agen.AUG_BATCH_SIZE * sample_size
                train_size = sample_size + sample_batch_size

                train_features = np.zeros((train_size, set.FEATURE_DIM))
                train_labels = np.zeros((train_size, ))

                for i in range(sample_size):
                    train_features[i] = uset.users[uidx]['samples'][i]['feature']
                    train_labels[i] = uset.users[uidx]['samples'][i]['label']
                    train_features[i+sample_size:i+sample_size+agen.AUG_BATCH_SIZE] = uset.users[uidx]['augments'][i]['feature']
                    train_labels[i+sample_size:i+sample_size+agen.AUG_BATCH_SIZE] = uset.users[uidx]['augments'][i]['label']

                # train_labels = to_categorical(train_labels, num_classes=2)
                if tset_name is None:
                    tset_name = t_train.classifier

                print("Training ... ", len(train_labels))
                t0 = time()
                model.train_model(train_features, train_labels, tset_name)
                t1 = time()
                print("Training took ", t1 - t0)

                data = {"success": 'pass'}
                db.set(q_uid, json.dumps(data))
                db.ltrim(set.REQUEST_QUEUE, len(q_uid), -1)

            if target == 'retrainView':

                m_checkpoints += 1
                # initialize augment
                agen = augments.Augments()

                uset.setIter(uidx, retrain_v.iter)

                print("Augment ... ", len(retrain_v.samples))
                t0 = time()
                for sample in retrain_v.samples:
                    # init sample and augment
                    init_sample = dict(
                        id=0, f_idx=0, checkpoints=0,
                        aurl=None, feature=None, label=0,
                        iteration=0, centX=0, centY=0,
                        slideIdx=0, slide=None
                    )
                    init_augment = dict(
                        id=[], checkpoints=[], feature=[], label=[]
                    )

                    # remove samples stored if it already exists
                    remove_idx = []
                    for u in range(len(uset.users[uidx]['samples'])):
                        if uset.users[uidx]['samples'][u]['id'] == sample['id']:
                            remove_idx.append(u)

                    for r in remove_idx:
                        uset.users[uidx]['samples'].pop(r)
                        uset.users[uidx]['augments'].pop(r)

                    # add feature
                    init_sample['id'] = sample['id']
                    init_sample['aurl'] = str(sample['aurl'])
                    init_sample['slide'] = str(sample['slide'])

                    slide_idx = dset.getSlideIdx(init_sample['slide'])
                    object_num = dset.getObjNum(slide_idx)
                    data_idx = dset.getDataIdx(slide_idx)
                    feature_set = dset.getFeatureSet(data_idx, object_num)
                    x_centroid_set = dset.getXcentroidSet(data_idx, object_num)
                    y_centroid_set = dset.getYcentroidSet(data_idx, object_num)
                    slideIdx_set = dset.getSlideIdxSet(data_idx, object_num)

                    c_idx = getIdx(
                        x_centroid_set.astype(np.float), y_centroid_set.astype(np.float), slideIdx_set.astype(np.int), np.float32(sample['centX']), np.float32(sample['centY']), slide_idx
                    )

                    f_idx = data_idx + c_idx

                    PCA = joblib.load(pcaPath)

                    init_sample['f_idx'] =  f_idx
                    init_sample['feature'] = feature_set[c_idx]
                    init_sample['label'] = 1 if sample['label'] == 1 else 0
                    init_sample['iteration'] = retrain_v.iter
                    init_sample['centX'] = sample['centX']
                    init_sample['centY'] = sample['centY']
                    init_sample['checkpoints'] = m_checkpoints

                    # add augment features
                    slide_idx = dset.getSlideIdx(init_sample['slide'])
                    slide_mean = dset.getWSI_Mean(slide_idx)
                    slide_std = dset.getWSI_Std(slide_idx)

                    a_imgs = agen.prepare_image(init_sample['aurl'], slide_mean, slide_std)
                    a_featureSet = iset.FC1_MODEL.predict(a_imgs)
                    a_featureSet = PCA.transform(a_featureSet)
                    a_labelSet = np.zeros((agen.AUG_BATCH_SIZE, )).astype(np.uint8)
                    a_idSet = []
                    a_checkpointSet = []
                    for i in range(agen.AUG_BATCH_SIZE):
                        a_idSet.append(init_sample['id'])
                        a_checkpointSet.append(init_sample['checkpoints'])
                    if init_sample['label'] > 0:
                        a_labelSet.fill(1)

                    init_augment['id'] = a_idSet
                    init_augment['feature'] = a_featureSet
                    init_augment['label'] = a_labelSet
                    init_augment['checkpoints'] = a_checkpointSet

                    uset.setAugmentData(uidx, init_augment)
                    uset.setTrainSampleData(uidx, init_sample)

                t1 = time()
                print("Augmentation took ", t1 - t0)
                sample_size = len(uset.users[uidx]['samples'])
                sample_batch_size = agen.AUG_BATCH_SIZE * sample_size
                train_size = sample_size + sample_batch_size

                train_features = np.zeros((train_size, set.FEATURE_DIM))
                train_labels = np.zeros((train_size, ))

                for i in range(sample_size):
                    train_features[i] = uset.users[uidx]['samples'][i]['feature']
                    train_labels[i] = uset.users[uidx]['samples'][i]['label']
                    train_features[i+sample_size:i+sample_size+agen.AUG_BATCH_SIZE] = uset.users[uidx]['augments'][i]['feature']
                    train_labels[i+sample_size:i+sample_size+agen.AUG_BATCH_SIZE] = uset.users[uidx]['augments'][i]['label']

                # train_labels = to_categorical(train_labels, num_classes=2)
                if tset_name is None:
                    tset_name = retrain_v.classifier

                t0 = time()
                model.train_model(train_features, train_labels, tset_name)
                t1 = time()
                print("Training took ", t1 - t0, " ", len(train_labels), "Samples")

                slide_idx = dset.getSlideIdx(retrain_v.slide)
                object_num = dset.getObjNum(slide_idx)
                data_idx = dset.getDataIdx(slide_idx)
                feature_set = dset.getFeatureSet(data_idx, object_num)
                x_centroid_set = dset.getXcentroidSet(data_idx, object_num)
                y_centroid_set = dset.getYcentroidSet(data_idx, object_num)

                print("Testing Start ... ")
                t0 = time()
                predictions = model.predict(feature_set)
                t1 = time()
                print("Predict took ", t1 - t0)

                object_idx = load(
                    retrain_v.left, retrain_v.right, retrain_v.top, retrain_v.bottom, x_centroid_set.astype(np.float), y_centroid_set.astype(np.float)
                )
                data = {}
                for i in object_idx:
                    data[str(x_centroid_set[i][0])+'_'+str(y_centroid_set[i][0])] = str(predictions[i])

                db.set(q_uid, json.dumps(data))
                db.ltrim(set.REQUEST_QUEUE, len(q_uid), -1)

            if target == 'retrainHeatmap':
                m_checkpoints += 1
                # initialize augment
                agen = augments.Augments()

                uset.setIter(uidx, retrain_h.iter)

                for sample in retrain_h.samples:
                    # init sample and augment
                    init_sample = dict(
                        id=0, f_idx=0, checkpoints=0,
                        aurl=None, feature=None, label=0,
                        iteration=0, centX=0, centY=0,
                        slideIdx=0, slide=None
                    )
                    init_augment = dict(
                        id=[], checkpoints=[], feature=[], label=[]
                    )

                    # remove samples stored if it already exists
                    remove_idx = []
                    for u in range(len(uset.users[uidx]['samples'])):
                        if uset.users[uidx]['samples'][u]['id'] == sample['id']:
                            remove_idx.append(u)

                    for r in remove_idx:
                        uset.users[uidx]['samples'].pop(r)
                        uset.users[uidx]['augments'].pop(r)

                    # add feature
                    init_sample['id'] = sample['id']
                    init_sample['aurl'] = str(sample['aurl'])
                    init_sample['slide'] = str(sample['slide'])

                    slide_idx = dset.getSlideIdx(init_sample['slide'])
                    object_num = dset.getObjNum(slide_idx)
                    data_idx = dset.getDataIdx(slide_idx)
                    feature_set = dset.getFeatureSet(data_idx, object_num)
                    x_centroid_set = dset.getXcentroidSet(data_idx, object_num)
                    y_centroid_set = dset.getYcentroidSet(data_idx, object_num)
                    slideIdx_set = dset.getSlideIdxSet(data_idx, object_num)

                    c_idx = getIdx(
                        x_centroid_set.astype(np.float), y_centroid_set.astype(np.float), slideIdx_set.astype(np.int), np.float32(sample['centX']), np.float32(sample['centY']), slide_idx
                    )

                    f_idx = data_idx + c_idx

                    PCA = joblib.load(pcaPath)

                    init_sample['f_idx'] =  f_idx
                    init_sample['feature'] = feature_set[c_idx]
                    init_sample['label'] = 1 if sample['label'] == 1 else 0
                    init_sample['iteration'] = retrain_h.iter
                    init_sample['centX'] = sample['centX']
                    init_sample['centY'] = sample['centY']
                    init_sample['checkpoints'] = m_checkpoints

                    # add augment features
                    slide_idx = dset.getSlideIdx(init_sample['slide'])
                    slide_mean = dset.getWSI_Mean(slide_idx)
                    slide_std = dset.getWSI_Std(slide_idx)

                    a_imgs = agen.prepare_image(init_sample['aurl'], slide_mean, slide_std)
                    a_featureSet = iset.FC1_MODEL.predict(a_imgs)
                    a_featureSet = PCA.transform(a_featureSet)
                    a_labelSet = np.zeros((agen.AUG_BATCH_SIZE, )).astype(np.uint8)
                    a_idSet = []
                    a_checkpointSet = []
                    for i in range(agen.AUG_BATCH_SIZE):
                        a_idSet.append(init_sample['id'])
                        a_checkpointSet.append(init_sample['checkpoints'])
                    if init_sample['label'] > 0:
                        a_labelSet.fill(1)

                    init_augment['id'] = a_idSet
                    init_augment['feature'] = a_featureSet
                    init_augment['label'] = a_labelSet
                    init_augment['checkpoints'] = a_checkpointSet

                    uset.setAugmentData(uidx, init_augment)
                    uset.setTrainSampleData(uidx, init_sample)

                sample_size = len(uset.users[uidx]['samples'])
                sample_batch_size = agen.AUG_BATCH_SIZE * sample_size
                train_size = sample_size + sample_batch_size

                train_features = np.zeros((train_size, set.FEATURE_DIM))
                train_labels = np.zeros((train_size, ))

                for i in range(sample_size):
                    train_features[i] = uset.users[uidx]['samples'][i]['feature']
                    train_labels[i] = uset.users[uidx]['samples'][i]['label']
                    train_features[i+sample_size:i+sample_size+agen.AUG_BATCH_SIZE] = uset.users[uidx]['augments'][i]['feature']
                    train_labels[i+sample_size:i+sample_size+agen.AUG_BATCH_SIZE] = uset.users[uidx]['augments'][i]['label']

                if tset_name is None:
                    tset_name = retrain_h.classifier

                t0 = time()
                model.train_model(train_features, train_labels, tset_name)
                t1 = time()
                print("Training took ", t1 - t0, " ", len(train_labels), "Samples")

                slide_idx = dset.getSlideIdx(retrain_h.slide)
                object_num = dset.getObjNum(slide_idx)
                data_idx = dset.getDataIdx(slide_idx)
                feature_set = dset.getFeatureSet(data_idx, object_num)
                x_centroid_set = dset.getXcentroidSet(data_idx, object_num)
                y_centroid_set = dset.getYcentroidSet(data_idx, object_num)

                print("Testing Start ... ")
                t0 = time()
                if set.IS_HEATMAP == False:
                    scores = model.predict_prob(feature_set)
                t1 = time()
                print("Predict took ", t1 - t0)
                # set x and y maps
                retrain_h.setXandYmap()
                # write heatmaps
                retrain_h.setHeatMap(x_centroid_set, y_centroid_set, scores)
                # get heatmap data
                data = retrain_h.getData(0)

                db.set(q_uid, json.dumps(data))
                db.ltrim(set.REQUEST_QUEUE, len(q_uid), -1)

            if target == 'cancel':

                uset.users = []
                uset.u_size = 0
                is_normal_loaded = True
                tset_name = None
                is_reloaded = False
                m_checkpoints = 0

                del select
                del finalize
                del viewer
                del retrain_v
                del retrain_h
                del heat
                del t_train
                del report_label

                model = networks.Network()
                model.init_model()
                # dset = dataset.Dataset(set.PATH_TO_SPECIAL)

                data = {"success": 'pass'}
                db.set(q_uid, json.dumps(data))
                db.ltrim(set.REQUEST_QUEUE, len(q_uid), -1)

            if target == 'reviewSave':
                # modify labels if they are changed on review tab
                for q_sample in q_samples:
                    for sample in uset.users[uidx]['samples']:
                        if sample['id'] == q_sample['id']:
                            sample['label'] = 1 if q_sample['label'] == 1 else 0

                    for sample in uset.users[uidx]['augments']:
                        if sample['id'][0] == q_sample['id']:
                            sample['label'][:] = 1 if q_sample['label'] == 1 else 0

                data = {"success": 'pass'}
                db.set(q_uid, json.dumps(data))
                db.ltrim(set.REQUEST_QUEUE, len(q_uid), -1)

if __name__ == "__main__":
    run()
