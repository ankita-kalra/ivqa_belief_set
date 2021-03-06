from __future__ import division
import tensorflow as tf
import numpy as np
import os
from util import save_json

from inference_utils import caption_generator
from inference_utils.question_generator_util import SentenceGenerator
from config import ModelConfig
from w2v_answer_encoder import AnswerEncoder

from mtl_data_fetcher import AttentionTestDataFetcher as Reader
from vaq_inference_wrapper import InferenceWrapper

from util import get_image_feature_root
import pylab as plt
from skimage.io import imread, imshow

# TEST_SET = 'test-dev'
TEST_SET = 'dev'

tf.flags.DEFINE_string("model_type", "VAQ-van",
                       "Select a model to train.")
tf.flags.DEFINE_string("checkpoint_dir", "model/vaq_%s",
                       "Model checkpoint file or directory containing a "
                       "model checkpoint file.")
tf.flags.DEFINE_string("model_trainset", "trainval",
                       "Which split is the model trained on")
FLAGS = tf.flags.FLAGS

tf.logging.set_verbosity(tf.logging.INFO)

_CONF = 0.0
END_TOKEN = 2


def token_to_sentence(to_sentence, inds):
    if inds.ndim == 1:
        inds = inds[np.newaxis, :]
    captions = []
    end_pos = (inds == END_TOKEN).argmax(axis=1)

    for i_s, e in zip(inds, end_pos):
        t_ids = i_s[:e].tolist()
        if len(t_ids) == 0:
            t_ids.append(END_TOKEN)
        s = to_sentence.index_to_question(t_ids)
        captions.append(s)
    return captions


def evaluate_question(result_file, subset='dev'):
    from eval_vqa_question import QuestionEvaluator
    from util import get_dataset_root
    vqa_data_root, _ = get_dataset_root()
    assert(subset in ['train', 'dev', 'val'])
    subset = 'train' if subset == 'train' else 'val'
    annotation_file = '%s/Annotations/mscoco_%s2014_annotations.json' % (vqa_data_root, subset)
    question_file = '%s/Questions/OpenEnded_mscoco_%s2014_questions.json' % (vqa_data_root, subset)

    evaluator = QuestionEvaluator(annotation_file, question_file)
    evaluator.evaluate(result_file)
    evaluator.save_results()


def show_image(image_id):
    im_root = get_image_feature_root()
    im_format = 'val2014/COCO_val2014_%012d.jpg'
    im_file = os.path.join(im_root, im_format % image_id)
    im = imread(im_file)
    if np.rank(im) == 2:
        im = np.tile(im[::, np.newaxis], [1, 1, 3])
    imshow(im)
    plt.draw()
    plt.show(block=False)


def test(checkpoint_path=None):
    config = ModelConfig()
    config.phase = 'other'
    config.model_type = FLAGS.model_type

    # build data reader
    reader = Reader(batch_size=1, subset='dev', output_attr=True, output_im=False,
                    output_qa=True, output_capt=False)
    if checkpoint_path is None:
        ckpt = tf.train.get_checkpoint_state(FLAGS.checkpoint_dir % FLAGS.model_type)
        checkpoint_path = ckpt.model_checkpoint_path

    # build and restore model
    model = InferenceWrapper()
    restore_fn = model.build_graph_from_config(config, checkpoint_path)

    sess = tf.Session(graph=tf.get_default_graph())
    tf.logging.info('Restore from model %s' % os.path.basename(checkpoint_path))
    restore_fn(sess)

    # Create the vocabulary.
    to_sentence = SentenceGenerator(trainset=FLAGS.model_trainset)
    ans_ctx = AnswerEncoder()
    generator = caption_generator.CaptionGenerator(model, to_sentence.question_vocab, beam_size=6)

    print('Running inference on split %s...' % TEST_SET)
    num_batches = reader.num_batches
    for i in range(num_batches):
        outputs = reader.get_test_batch()
        im_feed, quest, _, ans_feed, quest_id, image_id = outputs
        if ans_feed == 2000:
            continue
        if i % 3 != 0:
            continue
        if i < 60:
            continue
        image_id = int(image_id)
        quest_id = int(quest_id)
        im_feed = np.squeeze(im_feed)
        quest = np.squeeze(quest)

        print('============== %d ============' % i)
        print('image id: %d, question id: %d' % (image_id, quest_id))
        print('question\t: %s' % to_sentence.index_to_question(quest.tolist()))
        show_image(image_id)
        while True:
            cmd = raw_input('Input answers for generation: enter c for next question, d for default answer:\n')
            cmd = str(cmd)
            if cmd == 'c':
                break
            elif cmd == 'd':
                ans_feed_tmp = ans_feed
            else:
                ans_feed_tmp = ans_ctx.get_nearest_top_answer_index(cmd)
                ans_feed_tmp = np.array(ans_feed_tmp).reshape(ans_feed.shape).astype(ans_feed.dtype)

            # generate answers
            captions = generator.beam_search(sess, [im_feed, ans_feed_tmp])
            # question = to_sentence.index_to_question(quest.tolist())
            answer = to_sentence.index_to_top_answer(ans_feed_tmp)

            # print('image id: %d, question id: %d' % (image_id, quest_id))
            # print('question\t: %s' % question)
            print('input answer\t: %s' % answer)
            tmp = []
            for c, g in enumerate(captions):
                quest_gen = to_sentence.index_to_question(g.sentence)
                tmp.append(quest_gen)
                print('<question %d>\t: %s' % (c, quest_gen))
            show_image(image_id)
            print('\n')

    #     caption = captions[0]
    #     sentence = to_sentence.index_to_question(caption.sentence)
    #     res_i = {'image_id': image_id, 'question_id': quest_id, 'question': sentence}
    #     results.append(res_i)
    # save_json(res_file, results)
    # return res_file


def main(_):

    def test_model(model_path):
        with tf.Graph().as_default():
            res_file = test(model_path)
        return evaluate_question(res_file, subset='dev')

    test_model(None)


if __name__ == '__main__':
    tf.app.run()
