# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'gui_new_shapefile.ui'
#
# Created by: PyQt5 UI code generator 5.9.2
#
# WARNING! All changes made in this file will be lost!

from PyQt5 import QtCore, QtGui, QtWidgets

class Ui_Dialog(object):
    def setupUi(self, Dialog):
        Dialog.setObjectName("Dialog")
        Dialog.resize(400, 300)
        self.buttonBox = QtWidgets.QDialogButtonBox(Dialog)
        self.buttonBox.setGeometry(QtCore.QRect(30, 240, 341, 32))
        self.buttonBox.setOrientation(QtCore.Qt.Horizontal)
        self.buttonBox.setStandardButtons(QtWidgets.QDialogButtonBox.Cancel|QtWidgets.QDialogButtonBox.Ok)
        self.buttonBox.setObjectName("buttonBox")
        self.label = QtWidgets.QLabel(Dialog)
        self.label.setGeometry(QtCore.QRect(10, 120, 121, 16))
        self.label.setObjectName("label")
        self.label_2 = QtWidgets.QLabel(Dialog)
        self.label_2.setGeometry(QtCore.QRect(10, 70, 91, 16))
        self.label_2.setObjectName("label_2")
        self.shapeNewFieldNameLE = QtWidgets.QLineEdit(Dialog)
        self.shapeNewFieldNameLE.setGeometry(QtCore.QRect(100, 120, 221, 20))
        self.shapeNewFieldNameLE.setObjectName("shapeNewFieldNameLE")
        self.shapeNewFileName = QtWidgets.QLineEdit(Dialog)
        self.shapeNewFileName.setGeometry(QtCore.QRect(100, 70, 221, 20))
        self.shapeNewFileName.setObjectName("shapeNewFileName")
        self.shapeNewFilePathBTN = QtWidgets.QToolButton(Dialog)
        self.shapeNewFilePathBTN.setGeometry(QtCore.QRect(330, 70, 25, 19))
        self.shapeNewFilePathBTN.setObjectName("shapeNewFilePathBTN")

        self.retranslateUi(Dialog)
        self.buttonBox.accepted.connect(Dialog.accept)
        self.buttonBox.rejected.connect(Dialog.reject)
        QtCore.QMetaObject.connectSlotsByName(Dialog)

    def retranslateUi(self, Dialog):
        _translate = QtCore.QCoreApplication.translate
        Dialog.setWindowTitle(_translate("Dialog", "Create New Shapefile"))
        self.label.setText(_translate("Dialog", "Field for Name:"))
        self.label_2.setText(_translate("Dialog", "New Shapefile:"))
        self.shapeNewFilePathBTN.setText(_translate("Dialog", "..."))

