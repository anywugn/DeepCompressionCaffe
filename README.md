# DeepCompressionCaffe
## 安装Docker
因为 caffe 1代框架太古老了很多依赖库都停止维护了，我们用docker比较省事。
在 Docker 环境下 `docker pull bvlc/caffe:cpu` 即可。
这里我们选择了纯cpu版本，这样可以避免麻烦的cuda版本问题，因为官方版本已经很久没更新过cuda支持了，貌似还停留在8.0，现在的新显卡肯定是跑不了的。
但是你也可以选择用英伟达维护的caffe框架，名字是nvcaffe，他们一直在适配新的cuda版本（目前到cuda 10.0?）在英伟达NGC平台可以免费下载
https://ngc.nvidia.com/catalog/containers/nvidia:caffe

附：推荐的进入docker的方式
```
docker exec -it [container id] bash
```

## 配置环境

安装神社2模组
```
pip install jinja2
```

设置环境变量, 第二条可以不用，顺便可以看到，caffe编译完的整套源码就在/opt/caffe里面
```
export CAFFE_ROOT=/opt/caffe
export SIMULATOR_ROOT=/opt/caffe
```

下载caffemodel格式的模型文件，因为这个库它不内置模型文件（版权问题？），下载完之后放到对应目录里，和prototxt放在一起就行了，比如：
```
wget -P $CAFFE_ROOT/models/bvlc_reference_caffenet/ http://dl.caffe.berkeleyvision.org/bvlc_reference_caffenet.caffemodel
```

然后就是下载我们dump的代码，虽然脚本里会自动切换到CAFFE_ROOT目录，但是我还是推荐直接把代码放到CAFFE_ROOT里去运行，因为我相对路径写的可能有点乱。

要切换模型的话，直接进代码里改路径就行了。
