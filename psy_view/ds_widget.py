# -*- coding: utf-8 -*-
"""ncview-like GUI to the psyplot framework"""
from itertools import cycle
import os.path as osp
import os

from PyQt5 import QtWidgets, QtGui
from PyQt5.QtCore import Qt
import psy_view.utils as utils
from psyplot_gui.content_widget import DatasetTreeItem
from psyplot_gui.common import DockMixin
from psyplot.data import get_filename_ds
from psy_view.rcsetup import rcParams

from matplotlib.animation import FuncAnimation

NOTSET = object


def get_icon(name, ending='.png'):
    return osp.join(osp.dirname(__file__), 'icons', name + ending)


class DatasetWidget(QtWidgets.QSplitter, DockMixin):
    """A widget to control the visualization of the variables in a dataset"""

    #: The title of the widget
    title = 'Stratigraphic plots'

    #: Display the dock widget at the right side of the GUI
    dock_position = Qt.RightDockWidgetArea

    _animating = False

    _ani = None

    ds_attr_columns = ['long_name', 'dims', 'shape']

    def __init__(self, ds, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.ds = ds

        self.setOrientation(Qt.Vertical)

        # first row: info label
        self.info_label = QtWidgets.QLabel("Select a variable to start")
        self.addWidget(self.info_label)

        # second row: dataset representation
        self.ds_tree = tree = QtWidgets.QTreeWidget()
        tree.setColumnCount(len(self.ds_attr_columns) + 1)
        tree.setHeaderLabels([''] + self.ds_attr_columns)
        ds_item = DatasetTreeItem(ds, self.ds_attr_columns, 0)
        fname = get_filename_ds(ds, False)[0]
        if fname is not None:
            fname = osp.basename(fname)
        else:
            fname = ''
        ds_item.setText(0, fname)
        tree.addTopLevelItem(ds_item)
        self.addWidget(tree)

        # third row, navigation
        self.navigation_box = QtWidgets.QHBoxLayout()

        # -- animate backwards button
        self.btn_animate_backward = utils.add_pushbutton(
            "◀◀", self.animate_backward,
            "Animate the time dimension backwards", self.navigation_box)
        self.btn_animate_backward.setCheckable(True)

        # -- go to previous button
        self.btn_prev = utils.add_pushbutton(
            '◀', self.go_to_previous_step,
            "Go to previous time step", self.navigation_box)

        # -- dimension menu for animation
        self.dimension_checkbox = QtWidgets.QComboBox()
        self.navigation_box.addWidget(self.dimension_checkbox)

        # -- go to next button
        self.btn_next = utils.add_pushbutton(
            '▶', self.go_to_next_step,
            "Go to next time step", self.navigation_box)

        # -- animate forward button
        self.btn_animate_forward = utils.add_pushbutton(
            "▶▶", self.animate_forward,
            "Animate the time dimension", self.navigation_box)
        self.btn_animate_forward.setCheckable(True)

        # -- interval slider
        self.sl_interval = QtWidgets.QSlider(Qt.Horizontal)
        self.sl_interval.setMinimum(40)  # 24 fps
        self.sl_interval.setMaximum(10000)
        self.sl_interval.setSingleStep(50)
        self.sl_interval.setPageStep(500)
        self.sl_interval.setValue(500)
        self.sl_interval.valueChanged.connect(self.reset_timer_interval)
        self.navigation_box.addWidget(self.sl_interval)

        # -- interval label
        self.lbl_interval = QtWidgets.QLabel('500 ms')
        self.navigation_box.addWidget(self.lbl_interval)

        self.addLayout(self.navigation_box)
        self.disable_navigation()

        # fourth row: plot interface
        self.formatoptions_box = QtWidgets.QHBoxLayout()

        self.btn_cmap = utils.add_pushbutton(
            rcParams["cmaps"][0], self.choose_next_colormap,
            "Select a different colormap", self.formatoptions_box)

        self.btn_cmap_settings = utils.add_pushbutton(
            get_icon('color_settings'), self.edit_color_settings,
            "Edit color settings", self.formatoptions_box,
            icon=True)
        self.btn_cmap_settings.setEnabled(False)

        self.btn_proj = utils.add_pushbutton(
            rcParams["projections"][0], self.choose_next_projection,
            "Change the basemap projection", self.formatoptions_box)

        self.btn_proj_settings = utils.add_pushbutton(
            get_icon('proj_settings'), self.edit_basemap_settings,
            "Edit basemap settings", self.formatoptions_box,
            icon=True)
        self.btn_proj_settings.setEnabled(False)

        self.btn_datagrid = utils.add_pushbutton(
            "Cells", self.toggle_datagrid,
            "Show the grid cell boundaries", self.formatoptions_box)
        self.btn_datagrid.setCheckable(True)
        self.btn_datagrid.setEnabled(False)

        self.btn_export = QtWidgets.QToolButton()
        self.btn_export.setText('Export')
        self.btn_export.setMenu(self.setup_export_menu())
        self.formatoptions_box.addWidget(self.btn_export)

        self.addLayout(self.formatoptions_box)

        # sixth row: variables
        self.variable_frame = QtWidgets.QGroupBox('Variables')
        ncols = 4
        self.variable_layout = QtWidgets.QGridLayout(self.variable_frame)
        self.variable_buttons = []
        for i, v in enumerate(ds):
            btn = utils.add_pushbutton(
                v, self._draw_variable(v), f"Visualize variable {v}")
            self.variable_buttons.append(btn)
            self.variable_layout.addWidget(btn, i // ncols, i % ncols)
        self.addWidget(self.variable_frame)

        # seventh row: dimensions
        self.dimension_table = QtWidgets.QTableWidget()
        self.addWidget(self.dimension_table)

    def clear_table(self):
        self.dimension_table.clear()
        self.dimension_table.setColumnCount(5)
        self.dimension_table.setHorizontalHeaderLabels(
            ['Type', 'First', 'Current', 'Last', 'Units'])

    def addLayout(self, layout):
        widget = QtWidgets.QWidget()
        widget.setLayout(layout)
        self.addWidget(widget)
        return widget

    def go_to_previous_step(self):
        dim = self.dimension_checkbox.currentText()
        self.increase_dim(dim, -1)()

    def go_to_next_step(self):
        dim = self.dimension_checkbox.currentText()
        self.increase_dim(dim)()

    def animate_backward(self):
        if self._animating:
            self.stop_animation()
            self.btn_animate_backward.setText('◀◀')
            self.enable_navigation()
        else:
            self._animate_forward = False
            self.btn_animate_backward.setText('■')
            self.disable_navigation(self.btn_animate_backward)
            self.start_animation()

    def animate_forward(self, event=None):
        if self._animating:
            self.stop_animation()
            self.btn_animate_forward.setText('▶▶')
            self.enable_navigation()
        else:
            self._animate_forward = True
            self.btn_animate_forward.setText('■')
            self.disable_navigation(self.btn_animate_forward)
            self.start_animation()

    def disable_navigation(self, but=None):
        for item in map(self.navigation_box.itemAt,
                        range(self.navigation_box.count())):
            w = item.widget()
            if w is not but and w is not self.sl_interval:
                w.setEnabled(False)

    def enable_navigation(self):
        for item in map(self.navigation_box.itemAt,
                        range(self.navigation_box.count())):
            w = item.widget()
            w.setEnabled(True)

    def disable_variables(self):
        for btn in self.variable_buttons:
            btn.setEnabled(False)

    def enable_variables(self):
        for btn in self.variable_buttons:
            btn.setEnabled(True)

    def toggle_datagrid(self):
        if self.btn_datagrid.isChecked():
            self.sp.update(datagrid='k--')
        else:
            self.sp.update(datagrid=None)

    def start_animation(self):
        self._animating = True
        self.disable_variables()
        if self._ani is None or self._ani.event_source is None:
            self._ani = FuncAnimation(
                self.fig, self.update_dims, frames=self.animation_frames(),
                init_func=self.sp.draw, interval=self.sl_interval.value())
            # HACK: Make sure that the animation starts although the figure
            # is already shown
            self._ani._draw_frame(next(self.animation_frames()))
        else:
            self._ani.event_source.start()

    def reset_timer_interval(self, value):
        self.lbl_interval.setText('%i ms' % value)
        if self._ani is None or self._ani.event_source is None:
            pass
        else:
            self._ani.event_source.stop()
            self._ani._interval = value
            self._ani.event_source.interval = value
            self._ani.event_source.start()

    def stop_animation(self):
        self._animating = False
        try:
            self._ani.event_source.stop()
        except AttributeError:
            pass
        self.enable_variables()
        self.refresh()

    def animation_frames(self):
        while self._animating:
            dim = self.dimension_checkbox.currentText()
            i = self.data.psy.idims[dim]
            imax = self.ds.dims[dim] - 1
            if self._animate_forward:
                i += -i if i == imax else 1
            else:
                i += imax if i == 0 else -1
            yield {dim: i}

    def update_dims(self, dims):
        self.sp.update(dims=dims)

    def choose_next_colormap(self):
        select = False
        nmaps = len(rcParams['cmaps'])
        current = self.btn_cmap.text()
        if self.sp and 'cmap' in self.sp.plotters[0]:
            invert_cmap = self.plotter.cmap.value.endswith('_r')
        else:
            invert_cmap = False
        for i, cmap in enumerate(cycle(rcParams['cmaps'])):
            if cmap == current:
                select = True
            elif select or i == nmaps:
                break
        self.btn_cmap.setText(cmap)
        if invert_cmap:
            cmap = cmap + '_r'
        if self.sp and 'cmap' in self.sp.plotters[0]:
            self.update_project(cmap=cmap)

    def edit_color_settings(self):
        CmapDialog.update_plotter(self.plotter)

    def choose_next_projection(self):
        select = False
        nprojections = len(rcParams['projections'])
        current = self.btn_proj.text()
        for i, proj in enumerate(cycle(rcParams['projections'])):
            if proj == current:
                select = True
            elif select or i == nprojections:
                break
        self.btn_proj.setText(proj)
        if self.sp and 'projection' in self.sp.plotters[0]:
            self.update_project(projection=proj)

    def edit_basemap_settings(self):
        BasemapDialog.update_plotter(self.plotter)

    def setup_export_menu(self):
        self.export_menu = menu = QtWidgets.QMenu()
        menu.addAction('image (PDF, PNG, etc.)', self.export_image)
        menu.addAction('animation (GIF, MP4, etc.', self.export_animation)
        menu.addAction('psyplot project (.pkl file)', self.export_project)
        menu.addAction('psyplot project with data',
                       self.export_project_with_data)
        menu.addAction('python script (.py)', self.export_python)
        return menu

    def export_image(self):
        fname, ok = QtWidgets.QFileDialog.getSaveFileName(
            self, "Export image", os.getcwd(),
            "Images (*.png *.pdf *.jpg *.svg)")
        if ok:
            self.sp.export(fname, rcParams['savefig_kws'])

    def export_animation(self):
        fname, ok = QtWidgets.QFileDialog.getSaveFileName(
            self, "Export animation", os.getcwd(),
            "Movie (*.mp4 *.mov *.gif)")
        if ok:
            self.animate_forward()
            self._ani.save(fname, **rcParams['animations.export_kws'],
                           fps=round(1000. / self.sl_interval.value()))
            self.animate_forward()

    def export_project(self):
        fname, ok = QtWidgets.QFileDialog.getSaveFileName(
            self, "Export project", os.getcwd(),
            "Psyplot projects (*.pkl)")
        if ok:
            self.sp.save_project(fname)

    def export_project_with_data(self):
        fname, ok = QtWidgets.QFileDialog.getSaveFileName(
            self, "Export project", os.getcwd(),
            "Psyplot projects (*.pkl)")
        if ok:
            self.sp.save_project(fname, ds_description={"ds"})

    def export_python(self):
        pass

    def _draw_variable(self, v):
        def func():
            """Visualize variable v"""
            self.variable = v
            self.make_plot()
            if self.sp is not None:
                self.refresh()
        return func

    _variable = NOTSET

    @property
    def variable(self):
        """The current variable"""
        return self._variable

    @variable.setter
    def variable(self, value):
        self._variable = value

    @property
    def available_plotmethods(self):
        v = self.variable
        if v is NOTSET:
            return []
        ret = []
        plot = self.ds.psy.plot
        for plotmethod in ['mapplot', 'plot2d', 'lineplot']:
            if plotmethod in plot._plot_methods:
                if getattr(plot, plotmethod).check_data(self.ds, v, {})[0]:
                    ret.append(plotmethod)
        return ret

    @property
    def plot(self):
        return getattr(self.ds.psy.plot, self.plotmethod)

    @property
    def plot_options(self):
        fmts = {}
        available_fmts = list(self.plot._plotter_cls._get_formatoptions())

        if 'cmap' in available_fmts:
            fmts['cmap'] = self.btn_cmap.text()

        var = self.ds[self.variable]
        if 'time' in var.dims:
            fmts['title'] = '%(time)s'
        if 'clabel' in available_fmts:
            if 'long_name' in var.attrs:
                fmts['clabel'] = '%(long_name)s'
            else:
                fmts['clabel'] = '%(name)s'
            if 'units' in var.attrs:
                fmts['clabel'] += ' %(units)s'

        return fmts


    plotmethod = None

    sp = None

    @property
    def data(self):
        return self.sp[0]

    @property
    def plotter(self):
        return self.data.psy.plotter

    @property
    def fig(self):
        if self.sp:
            return list(self.sp.figs)[0]

    def make_plot(self):
        plotmethods = self.available_plotmethods
        if not plotmethods:
            QtWidgets.QMessageBox.critical(
                self, "Visualization impossible",
                f"Found no plotmethod for variable {self.variable}")
            return
        old_plotmethod = self.plotmethod
        plotmethod, ok = QtWidgets.QInputDialog.getItem(
            self, "Choose a plot method", "Plot method:", plotmethods)
        if not ok:
            return
        else:
            self.plotmethod = plotmethod
        if old_plotmethod != self.plotmethod and self.sp is not None:
            self.sp.close(True, True, True)
            self.sp = None

        if self.sp is not None:
            self.sp.update(name=self.variable, **self.plot_options)
            self.show_fig()
        else:
            self._ani = None
            self.sp = self.plot(name=self.variable, **self.plot_options)
            self.sp.show()
        self.enable_navigation()

    def show_fig(self):
        self.fig.canvas.window().show()

    def refresh(self):
        data = self.sp[0]
        ds_data = self.ds[self.variable]

        table = self.dimension_table
        self.clear_table()
        dims = ds_data.dims
        table.setRowCount(ds_data.ndim)
        table.setVerticalHeaderLabels(ds_data.dims)

        # set time, z, x, y info
        for c in 'XYTZ':
            cname = ds_data.psy.get_dim(c)
            if cname and cname in dims:
                table.setItem(
                    dims.index(cname), 0, QtWidgets.QTableWidgetItem(c))

        for i, dim in enumerate(dims):
            coord = self.ds[dim]
            if 'units' in coord.attrs:
                table.setItem(
                    i, 4, QtWidgets.QTableWidgetItem(
                        str(coord.attrs['units'])))
            try:
                coord = list(map("{:1.4f}".format, coord.values))
            except (ValueError, TypeError):
                try:
                    coord = coord.to_pandas().dt.to_pydatetime()
                except AttributeError:
                    coord = list(map(str, coord.values))
                else:
                    coord = [t.isoformat() for t in coord]
            first = coord[0]
            last = coord[-1]
            table.setItem(
                i, 1, QtWidgets.QTableWidgetItem(first))
            table.setItem(
                i, 3, QtWidgets.QTableWidgetItem(last))

            current = data.psy.idims.get(dim)
            if current is not None and isinstance(current, int):
                table.setCellWidget(
                    i, 2, self.new_dimension_button(dim, coord[current]))

        table.resizeColumnsToContents()

        # update animation checkbox
        idims = data.psy.idims
        dims_to_animate = [dim for dim in dims
                           if isinstance(idims[dim], int)]
        self.btn_cmap_settings.setEnabled('cmap' in self.plotter)
        self.btn_proj_settings.setEnabled('projection' in self.plotter)
        self.btn_datagrid.setEnabled('datagrid' in self.plotter)

        current_dims_to_animate = list(map(
            self.dimension_checkbox.itemText,
            range(self.dimension_checkbox.count())))
        if dims_to_animate != current_dims_to_animate:
            self.dimension_checkbox.clear()
            self.dimension_checkbox.addItems(dims_to_animate)

    def new_dimension_button(self, dim, label):
        i = self.data.psy.idims[dim]
        imax = self.ds.dims[dim]
        btn = utils.QRightPushButton(label)
        if i < imax - 1:
            btn.clicked.connect(self.increase_dim(dim))
        if i > 0:
            btn.rightclicked.connect(self.increase_dim(dim, -1))
        btn.setToolTip(f"Increase dimension {dim} with left-click, and "
                       "decrease with right-click.")
        return btn

    def update_project(self, *args, **kwargs):
        self.sp.update(*args, **kwargs)
        self.refresh()

    def increase_dim(self, dim, increase=1):
        def update():
            i = self.data.psy.idims[dim]
            self.update_project(dims={dim: i+increase})
        return update


class BasemapDialog(QtWidgets.QDialog):
    """A dialog to modify the basemap settings"""

    def __init__(self, plotter, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.button_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel,
            self)
        vbox = QtWidgets.QVBoxLayout(self)

        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)

        proj_box = QtWidgets.QGroupBox("Projection settings")
        layout = QtWidgets.QFormLayout(proj_box)

        self.txt_clon = QtWidgets.QLineEdit()
        self.txt_clon.setPlaceholderText('auto')
        self.txt_clon.setToolTip('Central longitude in degrees East')
        self.txt_clon.setValidator(QtGui.QDoubleValidator(-360, 360, 7))
        layout.addRow('Central longitude: ', self.txt_clon)

        self.txt_clat = QtWidgets.QLineEdit()
        self.txt_clat.setPlaceholderText('auto')
        self.txt_clat.setToolTip('Central latitude in degrees North')
        self.txt_clat.setValidator(QtGui.QDoubleValidator(-90, 90, 7))
        layout.addRow('Central latitude: ', self.txt_clat)

        vbox.addWidget(proj_box)

        self.lsm_box = QtWidgets.QGroupBox('Coastlines')
        self.lsm_box.setCheckable(True)
        hbox = QtWidgets.QHBoxLayout(self.lsm_box)
        hbox.addWidget(QtWidgets.QLabel("Resolution:"))
        self.opt_110 = QtWidgets.QRadioButton("110m")
        self.opt_50 = QtWidgets.QRadioButton("50m")
        self.opt_10 = QtWidgets.QRadioButton("10m")
        hbox.addWidget(self.opt_110)
        hbox.addWidget(self.opt_50)
        hbox.addWidget(self.opt_10)

        vbox.addWidget(self.lsm_box)

        self.meridionals_box = QtWidgets.QGroupBox('Meridionals')
        self.meridionals_box.setCheckable(True)
        self.opt_meri_auto = QtWidgets.QRadioButton("auto")

        self.opt_meri_at = QtWidgets.QRadioButton("At:")
        self.txt_meri_at = QtWidgets.QLineEdit()
        self.txt_meri_at.setPlaceholderText("30, 60, 90, 120, ... °E")
        # TODO: Add validator

        self.opt_meri_every = QtWidgets.QRadioButton("Every:")
        self.txt_meri_every = QtWidgets.QLineEdit()
        self.txt_meri_every.setPlaceholderText("30 °E")
        self.txt_meri_every.setValidator(QtGui.QDoubleValidator(-360, 360, 7))

        self.opt_meri_num = QtWidgets.QRadioButton("Number:")
        self.txt_meri_num = QtWidgets.QLineEdit()
        self.txt_meri_num.setPlaceholderText("5")
        self.txt_meri_num.setValidator(QtGui.QIntValidator(1, 360))

        form = QtWidgets.QFormLayout(self.meridionals_box)
        form.addRow(self.opt_meri_auto)
        form.addRow(self.opt_meri_at, self.txt_meri_at)
        form.addRow(self.opt_meri_every, self.txt_meri_every)
        form.addRow(self.opt_meri_num, self.txt_meri_num)

        vbox.addWidget(self.meridionals_box)

        self.parallels_box = QtWidgets.QGroupBox('Parallels')
        self.parallels_box.setCheckable(True)
        self.opt_para_auto = QtWidgets.QRadioButton("auto")

        self.opt_para_at = QtWidgets.QRadioButton("At:")
        self.txt_para_at = QtWidgets.QLineEdit()
        self.txt_para_at.setPlaceholderText("-60, -30, 0, 30, ... °N")
        # TODO: Add validator

        self.opt_para_every = QtWidgets.QRadioButton("Every:")
        self.txt_para_every = QtWidgets.QLineEdit()
        self.txt_para_every.setPlaceholderText("30 °N")
        self.txt_para_every.setValidator(QtGui.QDoubleValidator(-90, 90, 7))

        self.opt_para_num = QtWidgets.QRadioButton("Number:")
        self.txt_para_num = QtWidgets.QLineEdit()
        self.txt_para_num.setPlaceholderText("5")
        self.txt_para_num.setValidator(QtGui.QIntValidator(1, 180))

        form = QtWidgets.QFormLayout(self.parallels_box)
        form.addRow(self.opt_para_auto)
        form.addRow(self.opt_para_at, self.txt_para_at)
        form.addRow(self.opt_para_every, self.txt_para_every)
        form.addRow(self.opt_para_num, self.txt_para_num)

        vbox.addWidget(self.parallels_box)

        vbox.addWidget(self.button_box)

        self.fill_from_plotter(plotter)

        for button in [self.opt_meri_at, self.opt_meri_auto, self.opt_meri_num,
                       self.opt_meri_every, self.opt_para_at,
                       self.opt_para_auto, self.opt_para_num,
                       self.opt_para_every]:
            button.clicked.connect(self.update_forms)

    def fill_from_plotter(self, plotter):
        if plotter.clon.value is not None:
            self.txt_clon.setText(str(plotter.clon.value))
        if plotter.clat.value is not None:
            self.txt_clat.setText(str(plotter.clat.value))

        if not plotter.lsm.value[0]:
            self.lsm_box.setChecked(False)
        else:
            try:
                res = plotter.lsm.value[0][:-1]
            except TypeError:
                res = '110'
            getattr(self, 'opt_' + res).setChecked(True)

        self.xgrid_value = None
        value = plotter.xgrid.value
        if not value:
            self.meridionals_box.setChecked(False)
        elif value is True:
            self.opt_meri_auto.setChecked(True)
        elif isinstance(value[0], str):
            self.xgrid_value = value[0]
            self.opt_meri_num.setChecked(True)
            self.txt_meri_num.setText(str(value[1]))
        elif isinstance(value, tuple):
            self.xgrid_value = value[:2]
            self.opt_meri_num.setChecked(True)
            steps = 11 if len(value) == 2 else value[3]
            self.txt_meri_num.setText(str(steps))
        else:
            self.opt_meri_at.setChecked(True)
            self.txt_meri_at.setText(', '.join(map(str, value)))

        self.ygrid_value = None
        value = plotter.ygrid.value
        if not value:
            self.parallels_box.setChecked(False)
        elif value is True:
            self.opt_para_auto.setChecked(True)
        elif isinstance(value[0], str):
            self.opt_para_num.setChecked(True)
            self.txt_para_num.setText(str(value[1]))
            self.ygrid_value = value[0]
        elif isinstance(value, tuple):
            self.ygrid_value = value[:2]
            self.opt_para_num.setChecked(True)
            steps = 11 if len(value) == 2 else value[3]
            self.txt_para_num.setText(str(steps))
        else:
            self.opt_para_at.setChecked(True)
            self.txt_para_at.setText(', '.join(map(str, value)))

    def update_forms(self):
        if self.meridionals_box.isChecked():
            self.txt_meri_at.setEnabled(self.opt_meri_at.isChecked())
            self.txt_meri_every.setEnabled(self.opt_meri_every.isChecked())
            self.txt_meri_num.setEnabled(self.opt_meri_num.isChecked())
        if self.parallels_box.isChecked():
            self.txt_para_at.setEnabled(self.opt_para_at.isChecked())
            self.txt_para_every.setEnabled(self.opt_para_every.isChecked())
            self.txt_para_num.setEnabled(self.opt_para_num.isChecked())

    @property
    def value(self):
        import numpy as np
        ret = {}
        ret['clon'] = None if not self.txt_clon.text().strip() else float(
            self.txt_clon.text().strip())
        ret['clat'] = None if not self.txt_clat.text().strip() else float(
            self.txt_clat.text().strip())

        if self.lsm_box.isChecked():
            if self.opt_110.isChecked():
                ret['lsm'] = '110m'
            elif self.opt_50.isChecked():
                ret['lsm'] = '50m'
            elif self.opt_10.isChecked():
                ret['lsm'] = '10m'
        else:
            ret['lsm'] = False

        if not self.meridionals_box.isChecked():
            ret['xgrid'] = False
        elif self.opt_meri_auto.isChecked():
            ret['xgrid'] = True
        elif self.opt_meri_every.isChecked():
            ret['xgrid'] = np.arange(
                -180, 180, float(self.txt_meri_every.text().strip() or 30))
        elif self.opt_meri_at.isChecked():
            ret['xgrid'] = list(map(
                float, self.txt_meri_at.text().split(','))) or False
        elif self.opt_meri_num.isChecked():
            if self.xgrid_value is None:
                ret['xgrid'] = ['rounded', int(self.txt_meri_num.text() or 5)]
            elif isinstance(self.xgrid_value, str):
                ret['xgrid'] = [self.xgrid_value,
                                int(self.txt_meri_num.text() or 5)]
            else:
                ret['xgrid'] = tuple(self.xgrid_value) + (
                    int(self.txt_meri_num.text() or 5), )

        if not self.parallels_box.isChecked():
            ret['ygrid'] = False
        elif self.opt_para_auto.isChecked():
            ret['ygrid'] = True
        elif self.opt_para_every.isChecked():
            ret['ygrid'] = np.arange(
                -180, 180, float(self.txt_para_every.text().strip() or 30))
        elif self.opt_para_at.isChecked():
            ret['ygrid'] = list(map(
                float, self.txt_para_at.text().split(','))) or False
        elif self.opt_para_num.isChecked():
            if self.ygrid_value is None:
                ret['ygrid'] = ['rounded', int(self.txt_para_num.text() or 5)]
            elif isinstance(self.ygrid_value, str):
                ret['ygrid'] = [self.ygrid_value,
                                int(self.txt_para_num.text() or 5)]
            else:
                ret['ygrid'] = tuple(self.ygrid_value) + (
                    int(self.txt_para_num.text() or 5), )
        return ret

    @classmethod
    def update_plotter(cls, plotter):
        dialog = cls(plotter)
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()
        dialog.exec_()
        if dialog.result() == QtWidgets.QDialog.Accepted:
            plotter.update(
                **dialog.value)


class CmapDialog(QtWidgets.QDialog):
    """A dialog to modify color bounds"""

    def __init__(self, plotter, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.button_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel,
            self)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        self.tabs = QtWidgets.QTabWidget()
        self.bounds_widget = BoundaryWidget(
            plotter.cmap.value, plotter.bounds.value)
        self.tabs.addTab(self.bounds_widget, "Colormap boundaries")

        vbox = QtWidgets.QVBoxLayout(self)
        vbox.addWidget(self.tabs)
        vbox.addWidget(self.button_box)

    @classmethod
    def update_plotter(cls, plotter):
        dialog = cls(plotter)
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()
        dialog.exec_()
        if dialog.result() == QtWidgets.QDialog.Accepted:
            plotter.update(
                **dialog.bounds_widget.value)


class BoundaryWidget(QtWidgets.QWidget):
    """A widget to select colormap boundaries"""

    def __init__(self, cmap_value, init_value, *args, **kwargs):
        super().__init__(*args, **kwargs)

        layout = QtWidgets.QGridLayout(self)

        self.type_box = QtWidgets.QGroupBox()
        vbox = QtWidgets.QVBoxLayout(self.type_box)
        self.opt_rounded = QtWidgets.QRadioButton("Rounded")
        self.opt_minmax = QtWidgets.QRadioButton("Exact")
        self.opt_custom = QtWidgets.QRadioButton("Custom")
        vbox.addWidget(self.opt_rounded)
        vbox.addWidget(self.opt_minmax)
        vbox.addWidget(self.opt_custom)

        layout.addWidget(self.type_box, 0, 0, 3, 1)

        self.min_box = QtWidgets.QGroupBox()
        hbox = QtWidgets.QHBoxLayout(self.min_box)
        self.opt_min = QtWidgets.QRadioButton("Minimum")
        self.opt_min_pctl = QtWidgets.QRadioButton("Percentile")
        self.txt_min_pctl = QtWidgets.QLineEdit()
        self.txt_min_pctl.setValidator(QtGui.QDoubleValidator(0., 100., 5))
        hbox.addWidget(self.opt_min)
        hbox.addWidget(self.opt_min_pctl)
        hbox.addWidget(self.txt_min_pctl)

        layout.addWidget(self.min_box, 0, 1, 1, 2)

        self.max_box = QtWidgets.QGroupBox()
        hbox = QtWidgets.QHBoxLayout(self.max_box)
        self.opt_max = QtWidgets.QRadioButton("Maximum")
        self.opt_max_pctl = QtWidgets.QRadioButton("Percentile")
        self.txt_max_pctl = QtWidgets.QLineEdit()
        self.txt_max_pctl.setValidator(QtGui.QDoubleValidator(0., 100., 5))
        hbox.addWidget(self.opt_max)
        hbox.addWidget(self.opt_max_pctl)
        hbox.addWidget(self.txt_max_pctl)

        layout.addWidget(self.max_box, 1, 1, 1, 2)

        self.txt_custom = QtWidgets.QLineEdit()
        self.txt_custom.setPlaceholderText('1, 2, 3, 4, 5, ...')
        # TODO: Add validator
        layout.addWidget(self.txt_custom, 2, 1, 1, 2)

        self.cb_symmetric = QtWidgets.QCheckBox("symmetric")
        layout.addWidget(self.cb_symmetric, 3, 0)

        self.cb_inverted = QtWidgets.QCheckBox("inverted")
        layout.addWidget(self.cb_inverted, 3, 1)
        self.cb_inverted.setChecked(cmap_value.endswith('_r'))
        self.init_cmap = cmap_value

        self.txt_levels = QtWidgets.QLineEdit()
        self.txt_levels.setInputMask(r"\B\o\u\n\d\s\: 900")
        self.txt_levels.setMaxLength(len('Bounds: 256'))
        layout.addWidget(self.txt_levels)

        self.fill_form(init_value)

        for button in [self.opt_minmax, self.opt_rounded, self.opt_custom,
                       self.opt_min, self.opt_max,
                       self.opt_min_pctl, self.opt_max_pctl]:
            button.clicked.connect(self.update_type)

    def update_type(self):
        custom = self.opt_custom.isChecked()
        self.txt_custom.setEnabled(custom)
        self.opt_min.setEnabled(not custom)
        self.opt_max.setEnabled(not custom)
        self.opt_min_pctl.setEnabled(not custom)
        self.opt_max_pctl.setEnabled(not custom)
        self.txt_min_pctl.setEnabled(self.opt_min_pctl.isChecked())
        self.txt_max_pctl.setEnabled(self.opt_max_pctl.isChecked())

    @property
    def value(self):
        cmap = self.init_cmap
        if self.cb_inverted.isChecked() and not cmap.endswith('_r'):
            cmap = cmap + '_r'
        elif not self.cb_inverted.isChecked() and cmap.endswith('_r'):
            cmap = cmap[:-2]
        if self.opt_custom.isChecked():
            bounds = list(map(float, self.txt_custom.text().split(',')))
            if not bounds:
                bounds = ['rounded', None]
        else:
            if self.opt_minmax.isChecked():
                val = 'minmax' if not self.cb_symmetric.isChecked() else 'sym'
            else:
                val = ('rounded' if not self.cb_symmetric.isChecked() else
                       'roundedsym')
            bounds = [val]
            levels = self.txt_levels.text()[len('Bounds: '):]
            bounds.append(int(levels) if levels.strip() else None)
            bounds.append(0 if self.opt_min.isChecked() else
                          float(self.txt_min_pctl.text().strip() or 0))
            bounds.append(100 if self.opt_max.isChecked() else
                          float(self.txt_max_pctl.text().strip() or 100))

        return {'bounds': bounds, 'cmap': cmap}



    def fill_form(self, value):

        if value[0] == 'rounded' or value[0] == 'roundedsym':
            self.opt_rounded.setChecked(True)
        elif value[0] == 'minmax' or value[0] == 'sym':
            self.opt_minmax.setChecked(True)
        else:
            self.opt_custom.setChecked(True)
            self.txt_custom.setText(', '.join(map(str, value)))
            self.txt_levels.setText('Bounds: %i' % len(value))
            return
        self.txt_levels.setText('Bounds: %s' % (value[1] or ''))
        self.txt_custom.setEnabled(False)

        min_pctl = 0 if len(value) <= 2 else value[2]
        if min_pctl == 0:
            self.opt_min.setChecked(True)
            self.txt_min_pctl.setText('0')
            self.txt_min_pctl.setEnabled(False)
        else:
            self.opt_min_pctl.setChecked(True)
            self.txt_min_pctl.setText(str(min_pctl))

        max_pctl = 100 if len(value) <= 3 else value[3]
        if max_pctl == 100:
            self.opt_max.setChecked(True)
            self.txt_max_pctl.setText('100')
            self.txt_max_pctl.setEnabled(False)
        else:
            self.opt_max_pctl.setChecked(True)
            self.txt_max_pctl.setText(str(max_pctl))

        self.cb_symmetric.setChecked(value[0].endswith('sym'))