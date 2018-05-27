import os
import argparse
import utils
import fur_model
import pandas as pd
import numpy as np
from functools import partial


import torch
import torch.nn as nn
from torchvision import models


model_names = sorted(name for name in fur_model.model_dict.keys())
parser = argparse.ArgumentParser(description='PyTorch ImageNet Training')

parser.add_argument('data', metavar='DIR',
                    help='path to dataset')
parser.add_argument('--checkpoint-file', default='/home/dingyang/best_val_weights.pth', type=str,
                    help='checkpoint file path (default: /home/dingyang/best_val_weights.pth)')
parser.add_argument('--model-name', '-a', metavar='ARCH', default='resnet18',
                    choices=model_names,
                    help='model architecture: ' +
                    ' | '.join(model_names) +
                    ' (default: resnet18)')
parser.add_argument('--batch-size', default=64, type=int,
                    metavar='N', help='mini-batch size (default: 256)')
parser.add_argument('--input-size', default=224, type=int,
                    help='net input size (default: 224)')
parser.add_argument('--add-size', default=224, type=int,
                    help='net add size (default: 32)')
parser.add_argument('--feature-file', default='', type=str,
                    help='feature file to save')


class Resnet152fts(nn.Module):
    def __init__(self, original_model):
        super(Resnet152fts, self).__init__()
        self.features = original_model.features

    def forward(self, x):
        x = self.features(x)
        return x.view(x.size(0), -1)


class InceptionResnetV2fts(nn.Module):
    def __init__(self, original_model):
        super().__init__()
        self.features = original_model.net.features
        self.pool = original_model.net.avgpool_1a

    def forward(self, x):
        x = self.features(x)
        x = self.pool(x)
        return x.view(x.size(0), -1)


class DPN98fts(nn.Module):
    def __init__(self, original_model):
        super(DPN98fts, self).__init__()
        self.features = original_model.net.features

    def forward(self, x):
        x = self.features(x)
        return x.view(x.size(0), -1)


class Inceptionv4fts(nn.Module):
    def __init__(self, original_model):
        super(InceptionAvgPool, self).__init__()
        self.features = original_model.net.features
        self.avg_pool = original_model.net.avg_pool

    def forward(self, x):
        x = self.features(x)
        x = self.avg_pool(x)
        return x


feature_extractor_dict = {
    'resnet152': Resnet152fts,
    'inceptionresnetv2': InceptionResnetV2fts,
    'dpn98': DPN98fts,
}


def get_feature_extractor(model_name, checkpoint_file):
    model = fur_model.get_model(model_name, False)
    fur_model.load_model(model, checkpoint_file)
    extractor_module = feature_extractor_dict[model_name](model)
    return extractor_module.cuda()


def extract_features(feature_extractor, data_dir, data_csv, prediction_file_path):

    print('[+] Using Ten-Crop Extracting strategy')
    input_size = args.input_size
    batch_size = args.batch_size
    add_size = args.add_size

    transform = utils.get_transforms(
        mode='test', input_size=input_size, resize_size=input_size+add_size)

    data_array = pd.read_csv(data_csv).values
    dataset = utils.DYDataSet(
        data_dir,
        data_array,
        transform
    )
    data_loader = torch.utils.data.DataLoader(
        dataset,
        batch_size=batch_size,
        shuffle=False,
        num_workers=4,
        pin_memory=True)

    feature_extractor = torch.nn.DataParallel(feature_extractor).cuda()
    feature_extractor.eval()

    all_labels = []
    all_fts = []

    with torch.no_grad():
        print('extracting total %d images' % len(dataset))

        for i, (input, labels) in enumerate(data_loader):  # tensor type
            print('extracting batch: %d/%d' %
                  (i, len(dataset)/batch_size))

            bs, ncrops, c, h, w = input.size()
            input = input.view(-1, c, h, w).cuda()
            output = feature_extractor(input)
            output = output.view(
                bs, ncrops, -1).mean(1).view(bs, -1)  # view to 2-D tensor
            all_labels.append(labels)
            all_fts.append(output.data.cpu())

            if((i+1) % 800 == 0):
                all_labels = torch.cat(
                    all_labels, dim=0).numpy().reshape(-1, 1)
                all_fts = torch.cat(all_fts, dim=0).numpy()

                print(f'[+] features shape: {all_fts.shape}')

                res = np.concatenate((all_fts, all_labels), axis=1)
                print(f'[+] save npy shape: {res.shape}')

                part = (i+1)/800
                fts_file_name = prediction_file_path+'.' + str(part)
                print('[+] writing fts file: %s, part %d ...' %
                      (fts_file_name, part))
                np.save(fts_file_name, res)

                all_labels = []
                all_fts = []

        all_labels = torch.cat(
            all_labels, dim=0).numpy().reshape(-1, 1)
        all_fts = torch.cat(all_fts, dim=0).numpy()

        print(f'[+] features shape: {all_fts.shape}')

        res = np.concatenate((all_fts, all_labels), axis=1)
        print(f'[+] save npy shape: {res.shape}')

        part = (int(len(dataset)/batch_size))/800+1
        fts_file_name = prediction_file_path+'.' + str(part)
        print('[+] writing fts file: %s, part %d ...' %
              (fts_file_name, part))
        np.save(fts_file_name, res)


def main():

    global args
    args = parser.parse_args()

    data_dir = os.path.join(args.data, 'train_ori')
    data_csv = os.path.join(args.data, 'train.csv')

    feature_extractor = get_feature_extractor(
        args.model_name, args.checkpoint_file)

    extract_features(feature_extractor, data_dir, data_csv, args.feature_file)


if __name__ == "__main__":
    main()