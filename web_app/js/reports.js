var tempUID = "5zeefce763e4d1.18563122";

$(function() {

	var	datasetslideSummary = $("#datasetSel"), trainsetSel = $("#trainsetSel"),
		downloadsetSel = $("#downloadsetSel"), datasetpredictDataset = $("#applyDatasetSel"),
		datasetpredictSlide = $('#datasetMapSel'), datasetLabel = $("#datasetLabelSel"),
		maskTrainSel = $('#trainsetLabelSel'), trainPath = "", pcaPath = "";

	// Populate Dataset dropdown
	//
	$.ajax({
		type: "POST",
		url: "db/getdatasets.php",
		data: {},
		dataType: "json",
		success: function(data) {

			var curDataset = data[0];
			pcaPath = curDataset[2];

			for( var item in data ) {
				datasetslideSummary.append(new Option(data[item][0], data[item][1]));
				datasetpredictSlide.append(new Option(data[item][0], data[item][1]));
				datasetpredictDataset.append(new Option(data[item][0], data[item][1]));
				datasetLabel.append(new Option(data[item][0], data[item][1]));
			}
			updateTrainSetsforSlideSummary(curDataset[0]);
			updateTrainSets(curDataset[0]);
			// updateSlideList();
			updateTrainSetsforPredictDataset(curDataset[0]);
			// updateTrainSetsforLabel(curDataset[0]);
			updateSlideListForLabel(curDataset[0]);
		}
	});

	// Populate training set dropdown
	//
	$.ajax({
		url: "db/getTrainingSets.php",
		data: "",
		dataType: "json",
		success: function(data) {
			for( var item in data ) {
				downloadsetSel.append(new Option(data[item][0], data[item][1]));
				maskTrainSel.append(new Option(data[item][0], data[item][1]));
			}
		}
	});

	// Need to montior changes for the map score select controls. Slide image
	//	size is dependant on these.
	//
	datasetslideSummary.change(updateslideSummary);
	datasetpredictSlide.change(updatepredictSlide);
	$("#slideMapSel").change(updateSlideSize);
	datasetpredictDataset.change(updatepredictDataset);
	datasetLabel.change(updateLabel);


	$("#label_form").on("submit", function(e){
		$('#maskDiag').modal('show');
		$('#maskprogressBar').css("width", '10%');

		var dataLabel = {};
		dataLabel['id'] = tempUID;
		dataLabel['uid'] = tempUID;
		dataLabel['target'] = 'label';
		dataLabel['pca'] = pcaPath;
		dataLabel['dataset'] = document.getElementById("datasetLabelSel").value;
		dataLabel['trainset'] = document.getElementById("trainsetLabelSel").value;
		dataLabel['slide'] = document.getElementById("slideLabelSel").value;
		dataLabel['left'] = document.getElementById("startx").value;
		dataLabel['top'] = document.getElementById("starty").value;
		dataLabel['width'] = document.getElementById("width").value;
		dataLabel['height'] = document.getElementById("height").value;

		$.ajax({
			 type: 'POST',
			 url: '/model/model/label',
			 data: JSON.stringify(dataLabel),
			 contentType: 'application/json;charset=UTF-8',
			 dataType: "json",
			 success: function(data){
				 $('#maskprogressBar').css("width", '80%');
				 	// var dt = JSON.parse(data);
				 	var dt = data;
				 	var link = document.createElement('a');
					var filename = dt['success'].split("/");
					link.href = dt['success'];
					link.download = filename[filename.length - 1];
					document.body.appendChild(link);
					link.click();
					$('#maskDiag').modal('hide');
			 },
			 error: function() {
				 console.log("Image failed");
			 }
		 });
		 e.preventDefault();
		});

		$("#count_form").on("submit", function(e){
			$('#countDiag').modal('show');
			$('#countprogressBar').css("width", '10%');
			var dataLabel = {};
			dataLabel['id'] = tempUID;
			dataLabel['uid'] = tempUID;
			dataLabel['target'] = 'count';
			dataLabel['pca'] = pcaPath;
			dataLabel['dataset'] = document.getElementById("datasetSel").value;
			for (var i = 0; i < downloadsetSel[0].length; i++) {
				if (document.getElementById("trainsetSel").value == downloadsetSel[0][i].innerHTML) {
						trainPath = downloadsetSel[0][i].value;
				}
			}
			dataLabel['trainset'] = trainPath;

			$.ajax({
				 type: 'POST',
				 url: '/model/model/count',
				 data: JSON.stringify(dataLabel),
				 contentType: 'application/json;charset=UTF-8',
				 dataType: "json",
				 success: function(data){
		 				$('#countprogressBar').css("width", '80%');
					 	// var dt = JSON.parse(data);
					 	var dt = data;
					 	var link = document.createElement('a');
						var filename = dt['success'].split("/");
						link.href = dt['success'];
						link.download = filename[filename.length - 1];
						document.body.appendChild(link);
						link.click();
						$('#countDiag').modal('hide');
				 },
				 error: function() {
					 console.log("Count failed");
				 }
			 });
			 e.preventDefault();
			});

			$("#map_form").on("submit", function(e){
				$('#mapDiag').modal('show');
				$('#mapprogressBar').css("width", '10%');
				var dataLabel = {};
				dataLabel['id'] = tempUID;
				dataLabel['uid'] = tempUID;
				dataLabel['target'] = 'map';
				dataLabel['pca'] = pcaPath;
				dataLabel['dataset'] = document.getElementById("datasetMapSel").value;

				for (var i = 0; i < downloadsetSel[0].length; i++) {
					if (document.getElementById("trainsetMapSel").value == downloadsetSel[0][i].innerHTML) {
							trainPath = downloadsetSel[0][i].value;
					}
				}

				dataLabel['trainset'] = trainPath;
				dataLabel['slide'] = document.getElementById("slideMapSel").value;

				$.ajax({
					 type: 'POST',
					 url: '/model/model/map',
					 data: JSON.stringify(dataLabel),
					 contentType: 'application/json;charset=UTF-8',
					 dataType: "json",
					 success: function(data){
			 				$('#mapprogressBar').css("width", '80%');
						 	// var dt = JSON.parse(data);
						 	var dt = data;
						 	var link = document.createElement('a');
							var filename = dt['success'].split("/");
							link.href = dt['success'];
							link.download = filename[filename.length - 1];
							document.body.appendChild(link);
							link.click();
							$('#mapDiag').modal('hide');
					 },
					 error: function() {
						 console.log("Count failed");
					 }
				 });
				 e.preventDefault();
				});


});

function downloadData(path){

	$.ajax({
			type:   "POST",
			url:    "python/label.php",
			data:   { path: path
							},
			success: function() {

			}
	});
}

function updateslideSummary() {
	var sel = document.getElementById('datasetSel'),
			  dataset = sel.options[sel.selectedIndex].label;
	updateTrainSetsforSlideSummary(dataset);
}

function updatepredictSlide() {
	var sel = document.getElementById('datasetMapSel'),
			  dataset = sel.options[sel.selectedIndex].label;
	updateTrainSets(dataset);
	// updateSlideList();
}

function updatepredictDataset() {
	var sel = document.getElementById('applyDatasetSel'),
			  dataset = sel.options[sel.selectedIndex].label;
	updateTrainSetsforPredictDataset(dataset);
}

function updateLabel() {
	var sel = document.getElementById('datasetLabelSel'),
			  dataset = sel.options[sel.selectedIndex].label;
	// updateTrainSetsforLabel(dataset);
	updateSlideListForLabel(dataset);
}


function updateTrainSetsforSlideSummary(dataSet) {

	$.ajax({
		type: "POST",
		url: "db/getTrainsetForDataset.php",
		data: { dataset: dataSet },
		dataType: "json",
		success: function(data) {

			var	reloadTrainSel = $("#trainsetSel");
			$("#trainsetSel").empty();

			for( var item in data.trainingSets ) {
				reloadTrainSel.append(new Option(data.trainingSets[item], data.trainingSets[item]));
			}
		}
	});

}


//
//	Updates the list of available slides for the current dataset
//
// function updateSlideList() {
//
// 	var	dataset = datasetMapSel.options[datasetMapSel.selectedIndex].label;
//
// 	// Get the list of slides for the current dataset
// 	$.ajax({
// 		type: "POST",
// 		url: "db/getslides.php",
// 		data: { dataset: dataset },
// 		dataType: "json",
// 		success: function(data) {
//
// 			$('#slideMapSel').empty();
// 			// Add the slides we have segmentation boundaries for to the dropdown
// 			// selector
// 			for( var item in data['slides'] ) {
// 				$('#slideMapSel').append(new Option(data['slides'][item], data['slides'][item]));
// 			}
// 			updateSlideSize();
// 		}
// 	});
// }



function updateTrainSets(dataSet) {

	$.ajax({
		type: "POST",
		url: "db/getTrainsetForDataset.php",
		data: { dataset: dataSet },
		dataType: "json",
		success: function(data) {

			var	reloadTrainSel = $("#trainsetMapSel");
			$("#trainsetMapSel").empty();

			for( var item in data.trainingSets ) {
				reloadTrainSel.append(new Option(data.trainingSets[item], data.trainingSets[item]));
			}
		}
	});

}



function updateTrainSetsforPredictDataset(dataSet) {

	$.ajax({
		type: "POST",
		url: "db/getTrainsetForDataset.php",
		data: { dataset: dataSet },
		dataType: "json",
		success: function(data) {

			var	reloadTrainSel = $("#applyTrainsetSel");
			$("#applyTrainsetSel").empty();

			for( var item in data.trainingSets ) {
				reloadTrainSel.append(new Option(data.trainingSets[item], data.trainingSets[item]));
			}
		}
	});

}




function updateSlideSize() {

	var	slide = slideMapSel.options[slideMapSel.selectedIndex].label;

	$.ajax({
		type: "POST",
		url: "db/getImgSize.php",
		data: { slide: slide },
		dataType: "json",
		success: function(data) {

			document.getElementById('imgSize').innerHTML = data[0]+" x "+data[1]+" pixels ";

			if( data[2] == 1 ) {
				document.getElementById('imgScale').innerHTML = "20x";
			} else if( data[2] == 2 ) {
				document.getElementById('imgScale').innerHTML = "40x";
			} else {
				document.getElementById('imgScale').innerHTML = "???";
			}
		}
	});
}



// function updateTrainSetsforLabel(dataSet) {
//
// 	$.ajax({
// 		type: "POST",
// 		url: "db/getTrainsetForDataset.php",
// 		data: { dataset: dataSet },
// 		dataType: "json",
// 		success: function(data) {
//
// 			var	reloadTrainSel = $("#trainsetLabelSel");
// 			$("#trainsetLabelSel").empty();
//
// 			for( var item in data.trainingSets ) {
// 				reloadTrainSel.append(new Option(data.trainingSets[item], data.trainingSets[item]));
// 			}
// 		}
// 	});
//
// }


//
//	Updates the list of available slides for the current dataset
//
function updateSlideListForLabel(dataset) {

	// Get the list of slides for the current dataset
	$.ajax({
		type: "POST",
		url: "db/getslides.php",
		data: { dataset: dataset },
		dataType: "json",
		success: function(data) {

			$('#slideLabelSel').empty();
			// Add the slides we have segmentation boundaries for to the dropdown
			// selector
			for( var item in data['slides'] ) {
				$('#slideLabelSel').append(new Option(data['slides'][item], data['slides'][item]));
			}
		}
	});
}



//
// Retruns the value of the GET request variable specified by name
//
//
function $_GET(name) {
	var match = RegExp('[?&]' + name + '=([^&]*)').exec(window.location.search);
	return match && decodeURIComponent(match[1].replace(/\+/g,' '));
}
