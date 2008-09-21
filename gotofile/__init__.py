# Gedit Go to File plugin.
# Copyright (C) 2008  Eric Butler <eric@extremeboredom.net>
#
# Based on "Snap Open" (C) 2006 Mads Buus Jensen <online@buus.net>
# Inspired by TextMate
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import gedit
import pygtk
import gtk, gobject, pango, gconf
import sexy
import os
import relevance
from urlparse import urlparse, urljoin

UI_STRING = """<ui>
<menubar name="MenuBar">
	<menu name="FileMenu" action="File">
		<placeholder name="FileOps_2">
			<menuitem name="GotoFile" action="GotoFileAction"/>
		</placeholder>
	</menu>
</menubar>
</ui>
"""

class GotoFilePluigin(gedit.Plugin):
	def __init__(self):
		gedit.Plugin.__init__(self)
		self._window = GotoFileWindow(self)
	
	def activate(self, window):
		self._geditWindow = window

		ui = window.get_ui_manager()
		self._actionGroup = gtk.ActionGroup('GotoFileActions')
		action = gtk.Action(name='GotoFileAction', label='Go to File...', tooltip='', stock_id=None)
		action.connect('activate', self._menuActivated)

		self._actionGroup.add_action_with_accel(action, '<Ctrl><Alt>o')
		ui.insert_action_group(self._actionGroup, 1)
		self._mergeId =  ui.add_ui_from_string(UI_STRING)

		self._window.set_transient_for(window)
	
	def deactivate(self, window):
		ui = window.get_ui_manager()
		ui.remove_ui(self._mergeId)
		ui.remove_action_group(self._actionGroup)
		self._geditWindow = None
	
	def getMaxDepth(self):
		return 5 # XXX: This should be configurable

	def getRootDirectory(self):
		fbRoot = self._getFilebrowserRoot()
		if fbRoot is not None and fbRoot != "":
			return fbRoot
		else:
			return os.getcwd()

	def _menuActivated(self, menu):
		self._window.show_all()
		self._window.present()

	def _getFilebrowserRoot(self):
	  base = '/apps/gedit-2/plugins/filebrowser/on_load'
	  client = gconf.client_get_default()
	  client.add_dir(base, gconf.CLIENT_PRELOAD_NONE)
	  path = base + '/virtual_root'
	  val = client.get(path)
	  if val is not None:
			url = urlparse(val.get_string())
			return url.path

	def openFile(self, path):
		uri = urljoin('file://', path)
		tab = self._geditWindow.get_tab_from_uri(uri)
		if tab == None:
			tab = self._geditWindow.create_tab_from_uri(uri, gedit.encoding_get_current(), 0, False, False)
		self._geditWindow.set_active_tab(tab)

class GotoFileWindow(gtk.Window):
	def __init__(self, plugin):
		gtk.Window.__init__(self)

		self._plugin = plugin

		self.set_title('Go to File')
		self.set_default_size(300, 250)
		self.set_type_hint(gtk.gdk.WINDOW_TYPE_HINT_UTILITY)
		self.set_position(gtk.WIN_POS_CENTER) # _ON_PARENT
		self.connect('show', self._windowShow)
		self.connect('delete-event', self._windowDeleteEvent)

		theme = gtk.icon_theme_get_default()
		searchPixbuf = theme.load_icon('search', 16, gtk.ICON_LOOKUP_USE_BUILTIN)

		self._entry = sexy.IconEntry()
		self._entry.add_clear_button()
		self._entry.set_icon(sexy.ICON_ENTRY_PRIMARY, gtk.image_new_from_pixbuf(searchPixbuf))
		self._entry.connect('changed', self._entryChanged)
		self._entry.connect('key-press-event', self._entryKeyPress)
		self._entry.connect('activate', self._entryActivated)

		cell = gtk.CellRendererText()
		cell.set_property('ellipsize', pango.ELLIPSIZE_START)

		self._tree = gtk.TreeView()
		self._tree.set_headers_visible(False)
		self._tree.append_column(gtk.TreeViewColumn("Name", cell, markup=0))
		self._tree.connect('button-press-event', self._treeButtonPress)
		self._tree.get_selection().connect('changed', self._treeSelectionChanged)

		# Model columns: formattedName, formattedPath, path, score
		self._store = gtk.ListStore(gobject.TYPE_STRING, gobject.TYPE_STRING, gobject.TYPE_STRING, gobject.TYPE_FLOAT)

		self._sortModel = gtk.TreeModelSort(self._store)
		self._sortModel.set_sort_column_id(3, gtk.SORT_DESCENDING)
		self._tree.set_model(self._sortModel)

		vbox = gtk.VBox()

		alignment = gtk.Alignment(0, 0, 1, 1)
		alignment.set_padding(6, 6, 6, 6)
		alignment.add(self._entry)
		vbox.pack_start(alignment, False, False, 0)

		vbox.pack_start(gtk.HSeparator(), False, False, 0)

		swindow = gtk.ScrolledWindow()
		swindow.set_policy(gtk.POLICY_NEVER, gtk.POLICY_AUTOMATIC)
		swindow.add(self._tree)
		vbox.pack_start(swindow, True, True, 0)

		vbox.pack_start(gtk.HSeparator(), False, False, 0)

		label = gtk.Label()
		#label.set_ellipsize(pango.ELLIPSIZE_START)
		self._expander = gtk.Expander(None)
		self._expander.set_label_widget(label)

		vbox.pack_start(self._expander, False, False, 0)

		self.add(vbox)

	def _windowShow(self, win):
		self._rootDirectory = self._plugin.getRootDirectory()
		self._entry.set_text('')
		self.search('')

	def _windowDeleteEvent(self, win, event):
		self.hide()
		return True
	
	def _entryActivated(self, entry):
		self.openSelectedFile()

	def _entryChanged(self, entry):
		 self.search(entry.get_text())

	def _entryKeyPress(self, entry, event):
		model, iter = self._tree.get_selection().get_selected()
		if iter:
			path = model.get_path(iter)
			if event.keyval == gtk.keysyms.Up:
				path = (path[0] - 1,)
				if path[0] >= 0:
					iter = model.get_iter(path)
					self._tree.get_selection().select_iter(iter)
				return True
			elif event.keyval == gtk.keysyms.Down:
				path = (path[0] + 1,)
				if path[0] < model.iter_n_children(None):
					iter = model.get_iter(path)
					self._tree.get_selection().select_iter(iter)
				return True
			elif event.keyval == gtk.keysyms.Escape:
				self.hide()
		return False
	
	def _treeButtonPress(self, tree, event):
		self.openSelectedFile()

	def _treeSelectionChanged(self, selection):
		model, iter = selection.get_selected()
		if iter:
			self._expander.get_label_widget().set_markup(model.get_value(iter, 1))
	
	def search(self, text):
		text = text.replace(' ', '')
		self._store.clear()

		# XXX: Don't walk deeper than self._plugin.getMaxDepth()
		# XXX: Ignore hidden (dot) directories
		for root, dirs, files in os.walk(self._rootDirectory):
			for file in files:
				score = relevance.score(file, text)
				if score > 0:
					name = relevance.formatCommonSubstrings(file, text)
					self._store.append((name, os.path.join(root, name), os.path.join(root, file), score))

		iter = self._sortModel.get_iter_first()
		if iter:
			self._tree.get_selection().select_iter(iter)
			path = self._sortModel.get_path(iter)
			self._tree.scroll_to_cell(path, None, True, 0, 0)
	
	def openSelectedFile(self):
		model, iter = self._tree.get_selection().get_selected()
		if iter:
			path = model.get_value(iter, 2)
			self._plugin.openFile(path)
			self.hide()
