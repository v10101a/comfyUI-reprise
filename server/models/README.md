`face_detection_yunet_2023mar.onnx` is the YuNet face detector from
[OpenCV Zoo](https://github.com/opencv/opencv_zoo/tree/main/models/face_detection_yunet),
under the adjacent MIT license. SHA-256:
`8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4`.

The head tracker uses a padded 320×320 input, compatible with the model's fixed
input size in both OpenCV 4 and 5. Inference runs locally; no runtime download.
