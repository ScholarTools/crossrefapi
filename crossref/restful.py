# coding: utf-8

#Standard
#------------------------
from time import sleep


#Third
#--------------------------
import requests

#Local
#-----------------------------
from . import validators, VERSION
from . import utils
fstr = utils.float_or_none_to_string
cld = utils.get_list_class_display
from .utils import get_truncated_display_string as td
from .utils import quotes

#Constants and Defaults
#--------------------------------
LIMIT = 100
MAXOFFSET = 10000
FACETS_MAX_LIMIT = 1000

API = "api.crossref.org"


class CrossrefAPIError(Exception):
    pass


class MaxOffsetError(CrossrefAPIError):
    pass


class UrlSyntaxError(CrossrefAPIError, ValueError):
    pass


class HTTPRequest(object):

    #??? This doesn't appear to be used
    THROTTLING_TUNNING_TIME = 600

    def __init__(self, throttle=True):
        """
        

        Parameters
        ----------
        throttle : default True
            ??? How is this implemented?

        Returns
        -------
        None.

        """
        self.throttle = throttle
        #This is a guess that impacts the default throttling time
        self.rate_limits = {
            'X-Rate-Limit-Limit': 50,
            'X-Rate-Limit-Interval': 1
        }

    def _update_rate_limits(self, headers):

        self.rate_limits['X-Rate-Limit-Limit'] = \
            int(headers.get('X-Rate-Limit-Limit', 50))

        interval_value = int(headers.get('X-Rate-Limit-Interval', '1s')[:-1])
        interval_scope = headers.get('X-Rate-Limit-Interval', '1s')[-1]

        if interval_scope == 'm':
            interval_value = interval_value * 60

        if interval_scope == 'h':
            interval_value = interval_value * 60 * 60

        self.rate_limits['X-Rate-Limit-Interval'] = interval_value

    @property
    def throttling_time(self):
        return self.rate_limits['X-Rate-Limit-Interval'] / self.rate_limits['X-Rate-Limit-Limit']

    def do_http_request(self, method, endpoint, data=None, 
                        files=None, timeout=100, only_headers=False, 
                        custom_header=None):

        if only_headers is True:
            return requests.head(endpoint)

        if method == 'post':
            action = requests.post
        else:
            action = requests.get

        if custom_header:
            headers = custom_header
        else:
            headers = {'user-agent': str(Etiquette())}
            
        if method == 'post':
            result = action(endpoint, data=data, files=files, timeout=timeout, 
                            headers=headers)
        else:
            result = action(endpoint, params=data, timeout=timeout, 
                            headers=headers)

        if self.throttle is True:
            self._update_rate_limits(result.headers)
            sleep(self.throttling_time)

        return result


def build_url_endpoint(endpoint, context=None):
    """
    
    Helper method to build url
    
    Parameters
    ----------
    endpoint : string
        API endpoint without query params
    context : string, default None
        a prefix to the endpoint, see funders

    Returns
    -------
    TYPE
        DESCRIPTION.

    """

    endpoint = '/'.join([i for i in [context, endpoint] if i])

    return 'https://%s/%s' % (API, endpoint)


class Etiquette:

    def __init__(self, 
                 application_name='undefined', 
                 application_version='undefined', 
                 application_url='undefined', 
                 contact_email='anonymous'):
        """
        etiquette = Etiquette(app_name,app_version,app_url,email)
        w = Works(etiquette=etiquette)
        
        """
        
        
        self.application_name = application_name
        self.application_version = application_version
        self.application_url = application_url
        self.contact_email = contact_email

    def __str__(self):

        return '%s/%s (%s; mailto:%s) BasedOn: CrossrefAPI/%s' % (
            self.application_name,
            self.application_version,
            self.application_url,
            self.contact_email,
            VERSION
        )


class Endpoint:

    #This varies by class type
    CURSOR_AS_ITER_METHOD = False
    
    """
    
    Attributes
    ----------
    context : string
        This seems to be used for getting works for specific funders. 
        e.g. /funders/{id}/works   => context = '%s/%s' % (self.ENDPOINT, str(funder_id))
    custom_header
    crossref_plus_token : string
        Plus token allows better performance (for a price)
    do_http_request : method
        This is the 'do_http_request' method of HTTPRequest
    etiquette : Etiquette
    request_params
    timeout    
    version
    
    
    """

    def __init__(self, 
                 request_url=None, 
                 request_params=None, 
                 context=None, 
                 etiquette=None, 
                 throttle=True, 
                 crossref_plus_token=None, 
                 timeout=30):
                
        self.context = context or ''
        self.crossref_plus_token = crossref_plus_token
        self.etiquette = etiquette or Etiquette()
        self.custom_header = {'user-agent': str(self.etiquette)}
        if crossref_plus_token:
            self.custom_header["Crossref-Plus-API-Token"] = self.crossref_plus_token
        
        #Note
        self.do_http_request = HTTPRequest(throttle=throttle).do_http_request
        
        self.request_params = request_params or dict()
        self.request_url = request_url or build_url_endpoint(self.ENDPOINT, context)
        self.timeout = timeout
        self._version = None
       
    @classmethod    
    def _create_copy(cls,old,request_url,request_params):
        
        
        #Select
        #return self.__class__(request_url=request_url, request_params=request_params, 
        #context=context, etiquette=self.etiquette, timeout=self.timeout)

        self = cls.__new__(cls)
        self.context = old.context
        self.crossref_plus_token = old.crossref_plus_token
        self.etiquette = old.etiquette
        self.custom_header = old.custom_header
        self.do_http_request = old.do_http_request
        self.request_params = request_params
        self.request_url = request_url
        self.timeout = old.timeout
        self._version = old._version
        
        return self

    @property
    def _rate_limits(self):
        """
        

        Returns
        -------
        rate_limits : dict
            DESCRIPTION.

        """
        #request_params = dict(self.request_params)
        request_url = str(self.request_url)

        result = self.do_http_request(
            'get',
            request_url,
            only_headers=True,
            custom_header=self.custom_header,
            timeout=self.timeout,
            throttle=False
        )

        rate_limits = {
            'X-Rate-Limit-Limit': result.headers.get('X-Rate-Limit-Limit', 'undefined'),
            'X-Rate-Limit-Interval': result.headers.get('X-Rate-Limit-Interval', 'undefined')
        }

        return rate_limits

    def _remove_paging_params(self):
        """
        
        Removes offset and rows from .request_params and returns the remaining
        request parameters as a dictionary. 
        
        Returns
        -------
        request_params : dict
            DESCRIPTION.

        """
        
        #These are removed from the dictionary
        paging_params = ['offset', 'rows']
        
        #rows - # of results per page
        #offset - # of results to skip before returning results
        
        request_params = dict(self.request_params)

        for item in paging_params:
            try:
                del(request_params[item])
            except KeyError:
                pass

        return request_params

    @property
    def version(self):
        """
            This attribute retrieve the API version.

            >>> Works().version
            '1.0.0'
        """
        
        if self._version is None: 
            request_params = dict(self.request_params)
            request_url = str(self.request_url)
    
            result = self.do_http_request(
                'get',
                request_url,
                data=request_params,
                custom_header=self.custom_header,
                timeout=self.timeout
            ).json()

            self._version =  result['message-version']
            
        return self._version

    @property
    def x_rate_limit_limit(self):

        return self._rate_limits.get('X-Rate-Limit-Limit', 'undefined')

    @property
    def x_rate_limit_interval(self):

        return self._rate_limits.get('X-Rate-Limit-Interval', 'undefined')

    def count(self):
        """
        This method retrieve the total of records resulting from a given query.

        This attribute can be used compounded with query, filter,
        sort, order and facet methods.

        Examples:
            >>> from crossref.restful import Works
            >>> Works().query('zika').count()
            3597
            >>> Works().query('zika').filter(prefix='10.1590').count()
            61
            >>> Works().query('zika').filter(prefix='10.1590').sort('published').order('desc').filter(has_abstract='true').count()
            14
            >>> Works().query('zika').filter(prefix='10.1590').sort('published').order('desc').filter(has_abstract='true').query(author='Marli').count()
            1
        
        Improvements
        ------------
        1) This request only returns the count. Do we expose the 
        raw message itself?
        
        
        """
        request_params = dict(self.request_params)
        request_url = str(self.request_url)
        request_params['rows'] = 0

        result = self.do_http_request(
            'get',
            request_url,
            data=request_params,
            custom_header=self.custom_header,
            timeout=self.timeout
        ).json()

        return int(result['message']['total-results'])

    @property
    def url(self):
        """
        This attribute retrieve the url that will be used as a HTTP request to
        the Crossref API.

        This attribute can be used compounded with query, filter,
        sort, order and facet methods.

        Examples:
            >>> from crossref.restful import Works
            >>> Works().query('zika').url
            'https://api.crossref.org/works?query=zika'
            >>> Works().query('zika').filter(prefix='10.1590').url
            'https://api.crossref.org/works?query=zika&filter=prefix%3A10.1590'
            >>> Works().query('zika').filter(prefix='10.1590').sort('published').order('desc').url
            'https://api.crossref.org/works?sort=published&order=desc&query=zika&filter=prefix%3A10.1590'
            >>> Works().query('zika').filter(prefix='10.1590').sort('published').order('desc').filter(has_abstract='true').query(author='Marli').url
            'https://api.crossref.org/works?sort=published&filter=prefix%3A10.1590%2Chas-abstract%3Atrue&query=zika&order=desc&query.author=Marli'
        """
        
        #TODO: This is an assumption ... - I would think we would want it
        request_params = self._remove_paging_params()

        sorted_request_params = sorted([(k, v) for k, v in request_params.items()])
        req = requests.Request(
            'get', self.request_url, params=sorted_request_params).prepare()

        return req.url

    def all(self):
        """
        Defaults back to endpoint without parameters.
        
        This could almost be called reset_endpoint() or clear_endpoint().
        
        But why the iter cast?

        Returns
        -------
        iterator
            DESCRIPTION.

        """
        context = str(self.context)
        request_url = build_url_endpoint(self.ENDPOINT, context)
        request_params = {}
        
        return iter(self._create_copy(self,request_url,request_params))

    
    def get(self):
        """
        
        THis can be used to get the raw response from the server. 

        Raises
        ------
        StopIteration
            DESCRIPTION.

        Returns
        -------
        json
            Response from the server. Contains fields:
                .status
                .message_type
                .message_version
                .message
                    .facets
                    .total-results
                    .items
                    .items-per_page
                    .query
            
        Improvements
        ------------
        1) Support returning an object that returns the data and facilitates
        getting more data
        
        

        """
        result = self.do_http_request(
                'get',
                self.request_url,
                data=self.request_params,
                custom_header=self.custom_header,
                timeout=self.timeout
            )

        if result.status_code == 404:
            raise StopIteration()

        return result.json()
    
    def __iter__(self):
        request_url = str(self.request_url)

        if 'sample' in self.request_params:
            request_params = self._remove_paging_params()
            result = self.do_http_request(
                'get',
                self.request_url,
                data=request_params,
                custom_header=self.custom_header,
                timeout=self.timeout
            )

            if result.status_code == 404:
                raise StopIteration()

            result = result.json()

            for item in result['message']['items']:
                yield item

            return

        if self.CURSOR_AS_ITER_METHOD is True:
            request_params = dict(self.request_params)
            #* is for deep paging, more than 10000 results
            request_params['cursor'] = '*'
            if 'rows' not in request_params:
                request_params['rows'] = LIMIT
            while True:
                result = self.do_http_request(
                    'get',
                    request_url,
                    data=request_params,
                    custom_header=self.custom_header,
                    timeout=self.timeout
                )

                if result.status_code == 404:
                    raise StopIteration()

                result = result.json()

                if len(result['message']['items']) == 0:
                    return

                for item in result['message']['items']:
                    yield item

                request_params['cursor'] = result['message']['next-cursor']
        else:
            #Relevant Endpoints 
            #--------------------------------
            #
            request_params = dict(self.request_params)
            if 'offset' not in request_params:
                request_params['offset'] = 0
            if 'rows' not in request_params:
                request_params['rows'] = LIMIT
            while True:
                result = self.do_http_request(
                    'get',
                    request_url,
                    data=request_params,
                    custom_header=self.custom_header,
                    timeout=self.timeout
                )

                if result.status_code == 404:
                    raise StopIteration()

                result = result.json()

                if len(result['message']['items']) == 0:
                    return

                for item in result['message']['items']:
                    yield item

                request_params['offset'] += LIMIT + 1

                if request_params['offset'] >= MAXOFFSET:
                    raise MaxOffsetError(
                        'Offset exceded the max offset of %d',
                        MAXOFFSET
                    )
                    
    def display_endpoint(self):
        """
        
            context : string
        This seems to be used for getting works for specific funders. 
        e.g. /funders/{id}/works   => context = '%s/%s' % (self.ENDPOINT, str(funder_id))
    custom_header
    crossref_plus_token : string
        Plus token allows better performance (for a price)
    do_http_request : method
        This is the 'do_http_request' method of HTTPRequest
    etiquette : Etiquette
    request_params
    timeout    
    version

        Returns
        -------
        TYPE
            DESCRIPTION.

        """
        
        if self._version is not None:
            version_string = self._version
        else:
            version_string = '<not yet evaluated>'
        
        pv = ['context',quotes(self.context),
              'custom_header',td(str(self.custom_header)),
              'crossref_plus_token',self.crossref_plus_token,
              'etiquette',cld(self.etiquette),
              'request_params',td(str(self.request_params)),
              'timeout',self.timeout,
              'url','<not evaluated>',
              'version',version_string,
              'methods()','------------------',
              'all()','returns object without request params',
              'get()','Returns json result without iterating',
              '__iter__()','Class can be iterated to return results']    
        
        print(utils.display_class(self,pv))



class Works(Endpoint):
    
    """
    
    https://api.crossref.org/swagger-ui/index.html#/Works
    
    Implements
    ----------
    /works/{doi} => doi
    /works => query
    /works/{doi}/agency
    
    """

    CURSOR_AS_ITER_METHOD = True

    ENDPOINT = 'works'

    ORDER_VALUES = ('asc', 'desc', '1', '-1')

    SORT_VALUES = (
        'created',
        'deposited',
        'indexed',
        'is-referenced-by-count',
        'issued',
        'published',
        'published-online',
        'published-print',
        'references-count',
        'relevance',
        'score',
        'submitted',
        'updated'
    )
    
    #TODO: It would be great to add a test that verifies this list
    #is up to date.
    """
    query.affiliation - query contributor affiliations
    query.author - query author given and family names
    query.bibliographic - query bibliographic information, useful for citation look up, includes titles, authors, ISSNs and publication years
    query.chair - query chair given and family names
    query.container-title - query container title aka. publication name
    query.contributor - query author, editor, chair and translator given and family names
    query.degree - query degree
    query.editor - query editor given and family names
    query.event-acronym - query acronym of the event
    query.event-location - query location of the event
    query.event-name - query name of the event
    query.event-sponsor - query sponsor of the event
    query.event-theme - query theme of the event
    query.funder-name - query name of the funder
    query.publisher-location - query location of the publisher
    query.publisher-name - query publisher name
    query.standards-body-acronym - query acronym of the standards body
    query.standards-body-name - query standards body name
    query.translator - query translator given and family names
    """

    FIELDS_QUERY = (
        'affiliation',
        'author',
        'bibliographic',
        'chair',
        'container_title',
        'contributor',
        'degree',
        'editor',
        'event_acronym',
        'event_location',
        'event_name',
        'event_sponsor',
        'event_theme',
        'funder_name',
        'publisher_location',
        'publisher_name',
        'standards_body_acronym',
        'standards_body_name',
        'translator'
    )

    FIELDS_SELECT = (
        'abstract',
        'URL',
        'member',
        'posted',
        'score',
        'created',
        'degree',
        'update-policy',
        'short-title',
        'license',
        'ISSN',
        'container-title',
        'issued',
        'update-to',
        'issue',
        'prefix',
        'approved',
        'indexed',
        'article-number',
        'clinical-trial-number',
        'accepted',
        'author',
        'group-title',
        'DOI',
        'is-referenced-by-count',
        'updated-by',
        'event',
        'chair',
        'standards-body',
        'original-title',
        'funder',
        'translator',
        'archive',
        'published-print',
        'alternative-id',
        'subject',
        'subtitle',
        'published-online',
        'publisher-location',
        'content-domain',
        'reference',
        'title',
        'link',
        'type',
        'publisher',
        'volume',
        'references-count',
        'ISBN',
        'issn-type',
        'assertion',
        'deposited',
        'page',
        'content-created',
        'short-container-title',
        'relation',
        'editor'
    )

    FILTER_VALIDATOR = {
        'alternative_id': None,
        'archive': validators.archive,
        'article_number': None,
        'assertion': None,
        'assertion-group': None,
        'award.funder': None,
        'award.number': None,
        'category-name': None,
        'clinical-trial-number': None,
        'container-title': None,
        'content-domain': None,
        'directory': validators.directory,
        'doi': None,
        'from-accepted-date': validators.is_date,
        'from-created-date': validators.is_date,
        'from-deposit-date': validators.is_date,
        'from-event-end-date': validators.is_date,
        'from-event-start-date': validators.is_date,
        'from-index-date': validators.is_date,
        'from-issued-date': validators.is_date,
        'from-online-pub-date': validators.is_date,
        'from-posted-date': validators.is_date,
        'from-print-pub-date': validators.is_date,
        'from-pub-date': validators.is_date,
        'from-update-date': validators.is_date,
        'full-text.application': None,
        'full-text.type': None,
        'full-text.version': None,
        'funder': None,
        'funder-doi-asserted-by': None,
        'group-title': None,
        'has-abstract': validators.is_bool,
        'has-affiliation': validators.is_bool,
        'has-archive': validators.is_bool,
        'has-assertion': validators.is_bool,
        'has-authenticated-orcid': validators.is_bool,
        'has-award': validators.is_bool,
        'has-clinical-trial-number': validators.is_bool,
        'has-content-domain': validators.is_bool,
        'has-domain-restriction': validators.is_bool,
        'has-event': validators.is_bool,
        'has-full-text': validators.is_bool,
        'has-funder': validators.is_bool,
        'has-funder-doi': validators.is_bool,
        'has-license': validators.is_bool,
        'has-orcid': validators.is_bool,
        'has-references': validators.is_bool,
        'has-relation': validators.is_bool,
        'has-update': validators.is_bool,
        'has-update-policy': validators.is_bool,
        'is-update': validators.is_bool,
        'isbn': None,
        'issn': None,
        'license.delay': validators.is_integer,
        'license.url': None,
        'license.version': None,
        'location': None,
        'member': validators.is_integer,
        'orcid': None,
        'prefix': None,
        'relation.object': None,
        'relation.object-type': None,
        'relation.type': None,
        'type': validators.document_type,
        'type-name': None,
        'until-accepted-date': validators.is_date,
        'until-created-date': validators.is_date,
        'until-deposit-date': validators.is_date,
        'until-event-end-date': validators.is_date,
        'until-event-start-date': validators.is_date,
        'until-index-date': validators.is_date,
        'until-issued-date': validators.is_date,
        'until-online-pub-date': validators.is_date,
        'until-posted-date': validators.is_date,
        'until-print-pub-date': validators.is_date,
        'until-pub-date': validators.is_date,
        'until-update-date': validators.is_date,
        'update-type': None,
        'updates': None
     }

    FACET_VALUES = {
        'archive': None,
        'affiliation': None,
        'assertion': None,
        'assertion-group': None,
        'category-name': None,
        'container-title': 1000,
        'license': None,
        'funder-doi': None,
        'funder-name': None,
        'issn': 1000,
        'orcid': 1000,
        'published': None,
        'publisher-name': None,
        'relation-type': None,
        'source': None,
        'type-name': None,
        'update-type': None
    }
    
    def rows(self,rows):
        
        context = str(self.context)
        request_url = build_url_endpoint(self.ENDPOINT, context)
        request_params = dict(self.request_params)
        
        #TODO: rows check
        
        request_params['rows'] = rows
        
        
        
        return self._create_copy(self, request_url, request_params)
    
    def offset(self,offset):
        
        context = str(self.context)
        request_url = build_url_endpoint(self.ENDPOINT, context)
        request_params = dict(self.request_params)
        
        #TODO: offset check
        
        request_params['offset'] = offset
        
        return self._create_copy(self, request_url, request_params)

    def order(self, order='asc'):
        """
        This method retrieve an iterable object that implements the method
        __iter__. The arguments given will compose the parameters in the
        request url.

        This method can be used compounded with query, filter,
        sort and facet methods.

        kwargs: valid SORT_VALUES arguments.

        return: iterable object of Works metadata

        Example 1:
            >>> from crossref.restful import Works
            >>> works.query('zika').sort('deposited').order('asc').url
            'https://api.crossref.org/works?sort=deposited&query=zika&order=asc'
            >>> query = works.query('zika').sort('deposited').order('asc')
            >>> for item in query:
            ...    print(item['title'], item['deposited']['date-time'])
            ...
            ['A Facile Preparation of 1-(6-Hydroxyindol-1-yl)-2,2-dimethylpropan-1-one'] 2007-02-13T20:56:13Z
            ['Contributions to the Flora of the Lake Champlain Valley, New York and Vermont, III'] 2007-02-13T20:56:13Z
            ['Pilularia americana A. Braun in Klamath County, Oregon'] 2007-02-13T20:56:13Z
            ...

        Example 2:
            >>> from crossref.restful import Works
            >>> works.query('zika').sort('deposited').order('desc').url
            'https://api.crossref.org/works?sort=deposited&query=zika&order=desc'
            >>> query = works.query('zika').sort('deposited').order('desc')
            >>> for item in query:
            ...    print(item['title'], item['deposited']['date-time'])
            ...
            ["Planning for the unexpected: Ebola virus, Zika virus, what's next?"] 2017-05-29T12:55:53Z
            ['Sensitivity of RT-PCR method in samples shown to be positive for Zika virus by RT-qPCR in vector competence studies'] 2017-05-29T12:53:54Z
            ['Re-evaluation of routine dengue virus serology in travelers in the era of Zika virus emergence'] 2017-05-29T10:46:11Z
            ...
        """

        context = str(self.context)
        request_url = build_url_endpoint(self.ENDPOINT, context)
        request_params = dict(self.request_params)

        if order not in self.ORDER_VALUES:
            raise UrlSyntaxError(
                'Sort order specified as %s but must be one of: %s' % 
                    (str(order), ', '.join(self.ORDER_VALUES)))

        request_params['order'] = order
    
        return self._create_copy(self, request_url, request_params)

    def select(self, *args):
        """
        This method retrieve an iterable object that implements the method
        __iter__. The arguments given will compose the parameters in the
        request url.

        This method can be used compounded with query, filter,
        sort and facet methods.

        args: valid FIELDS_SELECT arguments.

        return: iterable object of Works metadata

        Example 1:
            >>> from crossref.restful import Works
            >>> works = Works()
            >>> for i in works.filter(has_funder='true', has_license='true').sample(5).select('DOI, prefix'):
            ...     print(i)
            ...
            {'DOI': '10.1016/j.jdiacomp.2016.06.005', 'prefix': '10.1016', 'member': 'http://id.crossref.org/member/78'}
            {'DOI': '10.1016/j.mssp.2015.07.076', 'prefix': '10.1016', 'member': 'http://id.crossref.org/member/78'}
            {'DOI': '10.1002/slct.201700168', 'prefix': '10.1002', 'member': 'http://id.crossref.org/member/311'}
            {'DOI': '10.1016/j.actbio.2017.01.034', 'prefix': '10.1016', 'member': 'http://id.crossref.org/member/78'}
            {'DOI': '10.1016/j.optcom.2013.11.013', 'prefix': '10.1016', 'member': 'http://id.crossref.org/member/78'}
            ...
        Example 2:
            >>> from crossref.restful import Works
            >>> works = Works()

            >>> for i in works.filter(has_funder='true', has_license='true').sample(5).select('DOI').select('prefix'):
            >>>     print(i)
            ...
            {'DOI': '10.1016/j.sajb.2016.03.010', 'prefix': '10.1016', 'member': 'http://id.crossref.org/member/78'}
            {'DOI': '10.1016/j.jneumeth.2009.08.017', 'prefix': '10.1016', 'member': 'http://id.crossref.org/member/78'}
            {'DOI': '10.1016/j.tetlet.2016.05.058', 'prefix': '10.1016', 'member': 'http://id.crossref.org/member/78'}
            {'DOI': '10.1007/s00170-017-0689-z', 'prefix': '10.1007', 'member': 'http://id.crossref.org/member/297'}
            {'DOI': '10.1016/j.dsr.2016.03.004', 'prefix': '10.1016', 'member': 'http://id.crossref.org/member/78'}
            ...
        Example: 3:
            >>> from crossref.restful import Works
            >>> works = Works()
            >>>: for i in works.filter(has_funder='true', has_license='true').sample(5).select(['DOI', 'prefix']):
            >>>      print(i)
            ...
            {'DOI': '10.1111/zoj.12146', 'prefix': '10.1093', 'member': 'http://id.crossref.org/member/286'}
            {'DOI': '10.1016/j.bios.2014.04.018', 'prefix': '10.1016', 'member': 'http://id.crossref.org/member/78'}
            {'DOI': '10.1016/j.cej.2016.10.011', 'prefix': '10.1016', 'member': 'http://id.crossref.org/member/78'}
            {'DOI': '10.1016/j.dci.2017.08.001', 'prefix': '10.1016', 'member': 'http://id.crossref.org/member/78'}
            {'DOI': '10.1016/j.icheatmasstransfer.2016.09.012', 'prefix': '10.1016', 'member': 'http://id.crossref.org/member/78'}
            ...
        Example: 4:
            >>> from crossref.restful import Works
            >>> works = Works()
            >>>: for i in works.filter(has_funder='true', has_license='true').sample(5).select('DOI', 'prefix'):
            >>>      print(i)
            ...
            {'DOI': '10.1111/zoj.12146', 'prefix': '10.1093', 'member': 'http://id.crossref.org/member/286'}
            {'DOI': '10.1016/j.bios.2014.04.018', 'prefix': '10.1016', 'member': 'http://id.crossref.org/member/78'}
            {'DOI': '10.1016/j.cej.2016.10.011', 'prefix': '10.1016', 'member': 'http://id.crossref.org/member/78'}
            {'DOI': '10.1016/j.dci.2017.08.001', 'prefix': '10.1016', 'member': 'http://id.crossref.org/member/78'}
            {'DOI': '10.1016/j.icheatmasstransfer.2016.09.012', 'prefix': '10.1016', 'member': 'http://id.crossref.org/member/78'}
            ...
        """

        context = str(self.context)
        request_url = build_url_endpoint(self.ENDPOINT, context)
        request_params = dict(self.request_params)

        select_args = []

        invalid_select_args = []
        for item in args:
            if isinstance(item, list):
                select_args += [i.strip() for i in item]

            if isinstance(item, str):
                select_args += [i.strip() for i in item.split(',')]

        invalid_select_args = set(select_args) - set(self.FIELDS_SELECT)

        if len(invalid_select_args) != 0:
            raise UrlSyntaxError(
                'Select field\'s specified as (%s) but must be one of: %s' % (
                    ', '.join(invalid_select_args),
                    ', '.join(self.FIELDS_SELECT)
                )
            )

        request_params['select'] = ','.join(
            sorted([i for i in set(request_params.get('select', '').split(',') + select_args) if i])
        )

        return self._create_copy(self, request_url, request_params)

    def sort(self, sort='score'):
        """
        This method retrieve an iterable object that implements the method
        __iter__. The arguments given will compose the parameters in the
        request url.

        This method can be used compounded with query, filter,
        order and facet methods.

        kwargs: valid SORT_VALUES arguments.

        return: iterable object of Works metadata

        Example 1:
            >>> from crossref.restful import Works
            >>> works = Works()
            >>> query = works.sort('deposited')
            >>> for item in query:
            ...     print(item['title'])
            ...
            ['Integralidade e transdisciplinaridade em equipes multiprofissionais na saúde coletiva']
            ['Aprendizagem em grupo operativo de diabetes: uma abordagem etnográfica']
            ['A rotatividade de enfermeiros e médicos: um impasse na implementação da Estratégia de Saúde da Família']
            ...

        Example 2:
            >>> from crossref.restful import Works
            >>> works = Works()
            >>> query = works.sort('relevance')
            >>> for item in query:
            ...     print(item['title'])
            ...
            ['Proceedings of the American Physical Society']
            ['Annual Meeting of the Research Society on Alcoholism']
            ['Local steroid injections: Comment on the American college of rheumatology guidelines for the management of osteoarthritis of the hip and on the letter by Swezey']
            ['Intraventricular neurocytoma']
            ['Mammography accreditation']
            ['Temporal lobe necrosis in nasopharyngeal carcinoma: Pictorial essay']
            ...
        """
        context = str(self.context)
        request_url = build_url_endpoint(self.ENDPOINT, context)
        request_params = dict(self.request_params)

        if sort not in self.SORT_VALUES:
            raise UrlSyntaxError(
                'Sort field specified as %s but must be one of: %s' % (
                    str(sort),
                    ', '.join(self.SORT_VALUES)
                )
            )

        request_params['sort'] = sort

        return self._create_copy(self, request_url, request_params)

    def filter(self, **kwargs):
        """
        This method retrieve an iterable object that implements the method
        __iter__. The arguments given will compose the parameters in the
        request url.

        This method can be used compounded and recursively with query, filter,
        order, sort and facet methods.

        kwargs: valid FILTER_VALIDATOR arguments.

        return: iterable object of Works metadata

        Example:
            >>> from crossref.restful import Works
            >>> works = Works()
            >>> query = works.filter(has_funder='true', has_license='true')
            >>> for item in query:
            ...     print(item['title'])
            ...
            ['Design of smiling-face-shaped band-notched UWB antenna']
            ['Phase I clinical and pharmacokinetic study of PM01183 (a tetrahydroisoquinoline, Lurbinectedin) in combination with gemcitabine in patients with advanced solid tumors']
            ...
        """
        context = str(self.context)
        request_url = build_url_endpoint(self.ENDPOINT, context)
        request_params = dict(self.request_params)

        for fltr, value in kwargs.items():
            decoded_fltr = fltr.replace('__', '.').replace('_', '-')
            if decoded_fltr not in self.FILTER_VALIDATOR.keys():
                raise UrlSyntaxError(
                    'Filter %s specified but there is no such filter for this route. Valid filters for this route are: %s' % (
                        str(decoded_fltr),
                        ', '.join(self.FILTER_VALIDATOR.keys())
                    )
                )

            if self.FILTER_VALIDATOR[decoded_fltr] is not None:
                self.FILTER_VALIDATOR[decoded_fltr](str(value))

            if 'filter' not in request_params:
                request_params['filter'] = decoded_fltr + ':' + str(value)
            else:
                request_params['filter'] += ',' + decoded_fltr + ':' + str(value)

        return self._create_copy(self, request_url, request_params)

    def facet(self, facet_name, facet_count=100):
        """
        
        
        

        Parameters
        ----------
        facet_name : TYPE
            DESCRIPTION.
        facet_count : TYPE, optional
            DESCRIPTION. The default is 100.

        Raises
        ------
        UrlSyntaxError
            DESCRIPTION.

        Returns
        -------
        TYPE
            DESCRIPTION.

        Improvements
        ------------
        1) does the API support multiple facets???? - not currently but it could
        2) This design seems to break from the others in not taking kwargs -
        presumably because only o

        """
        context = str(self.context)
        request_url = build_url_endpoint(self.ENDPOINT, context)
        request_params = dict(self.request_params)
        request_params['rows'] = 0

        if facet_name not in self.FACET_VALUES.keys():
            facet_keys = self.FACET_VALUES.keys()
            raise UrlSyntaxError(
                'Facet %s specified but there is no such facet for this route. Valid facets for this route are: %s' % 
                    str(facet_name),
                    ', '.join(facet_keys)
                )

        #TODO: Yikes
        facet_count = self.FACET_VALUES[facet_name] if self.FACET_VALUES[facet_name] is not None\
            and self.FACET_VALUES[facet_name] <= facet_count else facet_count

        request_params['facet'] = '%s:%s' % (facet_name, facet_count)
        
        #TODO: Yikes, didn't realize this makes a request
        result = self.do_http_request(
            'get',
            request_url,
            data=request_params,
            custom_header=self.custom_header,
            timeout=self.timeout
        ).json()

        #This gets returns in addition to a message ... which is presumably
        #why this is terminal, because everywhere else we are assuming items
        return result['message']['facets']

    def query(self, *args, **kwargs):
        """
        This method retrieve an iterable object that implements the method
        __iter__. The arguments given will compose the parameters in the
        request url.

        This method can be used compounded and recursively with query, filter,
        order, sort and facet methods.

        args: strings (String)

        kwargs: valid FIELDS_QUERY arguments.

        return: iterable object of Works metadata

        Example:
            >>> from crossref.restful import Works
            >>> works = Works()
            >>> query = works.query('Zika Virus')
            >>> query.url
            'https://api.crossref.org/works?query=Zika+Virus'
            >>> for item in query:
            ...     print(item['title'])
            ...
            ['Zika Virus']
            ['Zika virus disease']
            ['Zika Virus: Laboratory Diagnosis']
            ['Spread of Zika virus disease']
            ['Carditis in Zika Virus Infection']
            ['Understanding Zika virus']
            ['Zika Virus: History and Infectology']
            ...
        """
        context = str(self.context)
        request_url = build_url_endpoint(self.ENDPOINT, context)
        request_params = dict(self.request_params)

        if args:
            request_params['query'] = ' '.join([str(i) for i in args])

        for field, value in kwargs.items():
            if field not in self.FIELDS_QUERY:
                if field == 'title':
                    raise UrlSyntaxError('title deprecated, use bibliographic instead, see https://status.crossref.org/incidents/4y45gj63jsp4')
                else:
                    raise UrlSyntaxError(
                        'Field query %s specified but there is no such field query for this route. Valid field queries for this route are: %s' % (
                            str(field), ', '.join(self.FIELDS_QUERY)
                        )
                    )
            request_params['query.%s' % field.replace('_', '-')] = value

        return self._create_copy(self, request_url, request_params)

    def sample(self, sample_size=20):
        """
        Return a random sampling of the results
        
        This method retrieve an iterable object that implements the method
        __iter__. The arguments given will compose the parameters in the
        request url.
        
        Parameters
        ----------
        sample_size : int, default 20
            value between 1 and 100

        Returns
        -------
        iterable object of Works metadata

        Example:
            >>> from crossref.restful import Works
            >>> works = Works()
            >>> works.sample(2).url
            'https://api.crossref.org/works?sample=2'
            >>> [i['title'] for i in works.sample(2)]
            [['A study on the hemolytic properties ofPrevotella nigrescens'],
            ['The geometry and the radial breathing mode of carbon nanotubes: beyond the ideal behaviour']]
        """
        
        context = str(self.context)
        request_url = build_url_endpoint(self.ENDPOINT, context)
        request_params = dict(self.request_params)

        try:
            if sample_size > 100:
                raise UrlSyntaxError(
                    'Integer specified as %s but must be a positive integer less than or equal to 100.' % str(sample_size)
                )
        except TypeError:
            raise UrlSyntaxError(
                'Integer specified as %s but must be a positive integer less than or equal to 100.' % str(sample_size)
            )

        request_params['sample'] = sample_size

        return self._create_copy(self, request_url, request_params)

    def doi(self, doi, only_message=True):
        """
        This method retrieve the DOI metadata related to a given DOI
        number.

        args: Crossref DOI id (String)

        return: JSON

        Example:
            >>> from crossref.restful import Works
            >>> works = Works()
            >>> works.doi('10.1590/S0004-28032013005000001')
            {'is-referenced-by-count': 6, 'reference-count': 216, 'DOI': '10.1590/s0004-28032013005000001',
            'subtitle': [], 'issued': {'date-parts': [[2013, 4, 19]]}, 'source': 'Crossref',
            'short-container-title': ['Arq. Gastroenterol.'], 'references-count': 216, 'short-title': [],
            'deposited': {'timestamp': 1495911725000, 'date-time': '2017-05-27T19:02:05Z',
            'date-parts': [[2017, 5, 27]]}, 'ISSN': ['0004-2803'], 'type': 'journal-article',
            'URL': 'http://dx.doi.org/10.1590/s0004-28032013005000001',
            'indexed': {'timestamp': 1496034748592, 'date-time': '2017-05-29T05:12:28Z',
            'date-parts': [[2017, 5, 29]]}, 'content-domain': {'crossmark-restriction': False, 'domain': []},
            'created': {'timestamp': 1374613284000, 'date-time': '2013-07-23T21:01:24Z',
            'date-parts': [[2013, 7, 23]]}, 'issn-type': [{'value': '0004-2803', 'type': 'electronic'}],
            'page': '81-96', 'volume': '50', 'original-title': [], 'subject': ['Gastroenterology'],
            'relation': {}, 'container-title': ['Arquivos de Gastroenterologia'], 'member': '530',
            'prefix': '10.1590', 'published-print': {'date-parts': [[2013, 4, 19]]},
            'title': ['3rd BRAZILIAN CONSENSUS ON Helicobacter pylori'],
            'publisher': 'FapUNIFESP (SciELO)', 'alternative-id': ['S0004-28032013000200081'],
            'abstract': '<jats:p>Significant abstract data.....  .</jats:p>',
            'author': [{'affiliation': [{'name': 'Universidade Federal de Minas Gerais,  BRAZIL'}],
            'family': 'Coelho', 'given': 'Luiz Gonzaga'}, {'affiliation': [
            {'name': 'Universidade Federal do Rio Grande do Sul,  Brazil'}], 'family': 'Maguinilk',
            'given': 'Ismael'}, {'affiliation': [
            {'name': 'Presidente de Honra do Núcleo Brasileiro para Estudo do Helicobacter,  Brazil'}],
            'family': 'Zaterka', 'given': 'Schlioma'}, {'affiliation': [
            {'name': 'Universidade Federal do Piauí,  Brasil'}], 'family': 'Parente', 'given': 'José Miguel'},
            {'affiliation': [{'name': 'Universidade Federal de Minas Gerais,  BRAZIL'}],
            'family': 'Passos', 'given': 'Maria do Carmo Friche'}, {'affiliation': [
            {'name': 'Universidade de São Paulo,  Brasil'}], 'family': 'Moraes-Filho',
            'given': 'Joaquim Prado P.'}], 'score': 1.0, 'issue': '2'}
        """
        request_url = build_url_endpoint(
            '/'.join([self.ENDPOINT, doi])
        )
        request_params = {}
        result = self.do_http_request(
            'get',
            request_url,
            data=request_params,
            custom_header=self.custom_header,
            timeout=self.timeout
        )

        if result.status_code == 404:
            return
        result = result.json()

        return result['message'] if only_message is True else result

    def agency(self, doi, only_message=True):
        """
        This method retrieve the DOI Agency metadata related to a given DOI
        number.
        
        Parameters
        ----------
        doi : string
        only_message : default True
            If true, only the message field of the result is returned, otherwise
            the entire result is returned.

        Returns
        -------
        return: JSON
        
        Implements
        ----------
        https://api.crossref.org/swagger-ui/index.html#/Works/get_works__doi__agency

        Example:
            >>> from crossref.restful import Works
            >>> works = Works()
            >>> works.agency('10.1590/S0004-28032013005000001')
            {'DOI': '10.1590/s0004-28032013005000001', 'agency': {'label': 'CrossRef', 'id': 'crossref'}}
        """
        request_url = build_url_endpoint(
            '/'.join([self.ENDPOINT, doi, 'agency'])
        )
        request_params = {}

        result = self.do_http_request(
            'get',
            request_url,
            data=request_params,
            custom_header=self.custom_header,
            timeout=self.timeout
        )

        if result.status_code == 404:
            return

        result = result.json()

        return result['message'] if only_message is True else result

    def doi_exists(self, doi):
        """
        This method retrieve a boolean according to the existence of a crossref
        DOI number. It returns False if the API results a 404 status code.

        args: Crossref DOI id (String)

        return: Boolean

        Example 1:
            >>> from crossref.restful import Works
            >>> works = Works()
            >>> works.doi_exists('10.1590/S0004-28032013005000001')
            True

        Example 2:
            >>> from crossref.restful import Works
            >>> works = Works()
            >>> works.doi_exists('10.1590/S0004-28032013005000001_invalid_doi')
            False
        """
        request_url = build_url_endpoint(
            '/'.join([self.ENDPOINT, doi])
        )
        request_params = {}

        result = self.do_http_request(
            'get',
            request_url,
            data=request_params,
            only_headers=True,
            custom_header=self.custom_header,
            timeout=self.timeout
        )

        if result.status_code == 404:
            return False

        return True
    
    
    def examples(self,example_type=None):
        
        #TODO: Finish this
        
        if example_type is None:
            print("Works().examples('agency')")
            print("Works().examples('doi')")
            print("Works().examples('query')")
            print("Works().examples('order')")
            print("Works().examples('select')")
            print("Works().examples('sort')")
            print("Works().examples('filter')")
            print("Works().examples('facet')")
            print("Works().examples('sample')")

            
            pass
        if example_type == 'agency':
            pass
        elif example_type == 'doi':
            print("result = Works().doi('10.1002/biot.201400046')")
        elif example_type == 'query':
            print("w = Works().query('Zika virus')")
            print("The search statement can be followed by keywords")
            print("to further refine the query. See Works.FIELDS_QUERY")
            print("for the list.")
            print("w = Works().query('electrical stimulation',affiliation='Duke').rows(5)")
            print("You can also omit the initial search")
            print("w = Works().query(author='Hokanson',title='Bladder').rows(5)")
            #['affiliation', 'author', 'bibliographic', 'chair', 'container_title', 'contributor', 'editor', 'event_acronym', 'event_location', 'event_name', 'event_sponsor', 'event_theme', 'funder_name', 'publisher_location', 'publisher_name', 'translator']
            pass
        elif example_type == 'order':
            print("w = Works().query('Zika virus')")
            pass
        elif example_type == 'select':
            #['DOI', 'ISBN', 'ISSN', 'URL', 'abstract', 'accepted', 'alternative-id', 'approved', 'archive', 'article-number', 'assertion', 'author', 'chair', 'clinical-trial-number', 'container-title', 'content-created', 'content-domain', 'created', 'degree', 'deposited', 'editor', 'event', 'funder', 'group-title', 'indexed', 'is-referenced-by-count', 'issn-type', 'issue', 'issued', 'license', 'link', 'member', 'original-title', 'page', 'posted', 'prefix', 'published-online', 'published-print', 'publisher', 'publisher-location', 'reference', 'references-count', 'relation', 'score', 'short-container-title', 'short-title', 'standards-body', 'subject', 'subtitle', 'title', 'translator', 'type', 'update-policy', 'update-to', 'updated-by', 'volume']

            pass
        elif example_type == 'sort':
            pass
        elif example_type == 'filter':
            pass
        elif example_type == 'facet':
            pass
        elif example_type == 'sample':
            pass
    
    def __repr__(self):

        pv = ['CURSOR_AS_ITER_METHOD',self.CURSOR_AS_ITER_METHOD,
              'ENDPOINT',quotes(self.ENDPOINT),
              'FACET_VALUES',td(str(self.FACET_VALUES)),
              'FIELDS_QUERY',td(str(self.FIELDS_QUERY)),
              'FIELDS_SELECT',td(str(self.FIELDS_SELECT)),
              'FILTER_VALIDATOR',td(str(self.FILTER_VALIDATOR)),
              'ORDER_VALUES',td(str(self.ORDER_VALUES)),
              'SORT_VALUES',td(str(self.SORT_VALUES)),
              'methods()','----------------------',
              'agency()','Get agency info for DOI',
              'count()','Returns # of results',
              'doi()','Get info for DOI',
              'query()','Get works based on query',
              'query-modifiers','-------------',
              'order()','how to order results',
              'select()','which fields to return',
              'sort()','how to sort results',
              'filter()','',
              'facet()','counts facets',
              'sample(n)','randomly samples from response',
              '--others--','------------------------',
              'display_endpoint()','displays endpoint props',
              'examples()','Displays calling examples'
              ]    
        
        return utils.display_class(self,pv) 


class Funders(Endpoint):

    CURSOR_AS_ITER_METHOD = False

    ENDPOINT = 'funders'

    FILTER_VALIDATOR = {
        'location': None,
    }

    def query(self, *args):
        """
        This method retrieve an iterable object that implements the method
        __iter__. The arguments given will compose the parameters in the
        request url.

        args: Funder ID (Integer)

        return: iterable object of Funders metadata

        Example:
            >>> from crossref.restful import Funders
            >>> funders = Funders()
            >>> funders.query('ABBEY').url
            'https://api.crossref.org/funders?query=ABBEY'
            >>> next(iter(funders.query('ABBEY')))
            {'alt-names': ['Abbey'], 'location': 'United Kingdom', 'replaced-by': [],
            'replaces': [], 'name': 'ABBEY AWARDS', 'id': '501100000314',
            'tokens': ['abbey', 'awards', 'abbey'],
            'uri': 'http://dx.doi.org/10.13039/501100000314'}
        """
        request_url = build_url_endpoint(self.ENDPOINT)
        request_params = dict(self.request_params)

        if args:
            request_params['query'] = ' '.join([str(i) for i in args])

        return self.__class__(request_url=request_url, request_params=request_params, etiquette=self.etiquette, timeout=self.timeout)

    def filter(self, **kwargs):
        """
        This method retrieve an iterable object that implements the method
        __iter__. The arguments given will compose the parameters in the
        request url.

        This method can be used compounded and recursively with query, filter,
        order, sort and facet methods.

        kwargs: valid FILTER_VALIDATOR arguments.

        return: iterable object of Funders metadata

        Example:
            >>> from crossref.restful import Funders
            >>> funders = Funders()
            >>> query = funders.filter(location='Japan')
            >>> for item in query:
            ...     print(item['name'], item['location'])
            ...
            (u'Central Research Institute, Fukuoka University', u'Japan')
            (u'Tohoku University', u'Japan')
            (u'Information-Technology Promotion Agency', u'Japan')
            ...
        """
        context = str(self.context)
        request_url = build_url_endpoint(self.ENDPOINT, context)
        request_params = dict(self.request_params)

        for fltr, value in kwargs.items():
            decoded_fltr = fltr.replace('__', '.').replace('_', '-')
            if decoded_fltr not in self.FILTER_VALIDATOR.keys():
                raise UrlSyntaxError(
                    'Filter %s specified but there is no such filter for this route. Valid filters for this route are: %s' % (
                        str(decoded_fltr),
                        ', '.join(self.FILTER_VALIDATOR.keys())
                    )
                )

            if self.FILTER_VALIDATOR[decoded_fltr] is not None:
                self.FILTER_VALIDATOR[decoded_fltr](str(value))

            if 'filter' not in request_params:
                request_params['filter'] = decoded_fltr + ':' + str(value)
            else:
                request_params['filter'] += ',' + decoded_fltr + ':' + str(value)

        return self.__class__(request_url=request_url, 
                              request_params=request_params, 
                              context=context, 
                              etiquette=self.etiquette, 
                              timeout=self.timeout)

    def funder(self, funder_id, only_message=True):
        """funder
        This method retrive a crossref funder metadata related to the
        given funder_id.

        args: Funder ID (Integer)

        Example:
            >>> from crossref.restful import Funders
            >>> funders = Funders()
            >>> funders.funder('501100000314')
            {'hierarchy': {'501100000314': {}}, 'alt-names': ['Abbey'],
            'work-count': 3, 'replaced-by': [], 'replaces': [],
            'hierarchy-names': {'501100000314': 'ABBEY AWARDS'},
            'uri': 'http://dx.doi.org/10.13039/501100000314', 'location': 'United Kingdom',
            'descendant-work-count': 3, 'descendants': [], 'name': 'ABBEY AWARDS',
            'id': '501100000314', 'tokens': ['abbey', 'awards', 'abbey']}
        """
        request_url = build_url_endpoint(
            '/'.join([self.ENDPOINT, str(funder_id)])
        )
        request_params = {}

        result = self.do_http_request(
            'get',
            request_url,
            data=request_params,
            custom_header=self.custom_header,
            timeout=self.timeout
        )

        if result.status_code == 404:
            return

        result = result.json()

        return result['message'] if only_message is True else result

    def funder_exists(self, funder_id):
        """
        This method retrieve a boolean according to the existence of a crossref
        funder. It returns False if the API results a 404 status code.

        args: Crossref Funder id (Integer)

        return: Boolean

        Example 1:
            >>> from crossref.restful import Funders
            >>> funders = Funders()
            >>> funders.funder_exists('501100000314')
            True

        Example 2:
            >>> from crossref.restful import Funders
            >>> funders = Funders()
            >>> funders.funder_exists('999999999999')
            False
        """
        request_url = build_url_endpoint(
            '/'.join([self.ENDPOINT, str(funder_id)])
        )
        request_params = {}

        result = self.do_http_request(
            'get',
            request_url,
            data=request_params,
            only_headers=True,
            custom_header=self.custom_header,
            timeout=self.timeout
        )

        if result.status_code == 404:
            return False

        return True

    def works(self, funder_id):
        """
        This method retrieve a iterable of Works of the given funder.

        args: Crossref allowed document Types (String)

        return: Works()
        """
        context = '%s/%s' % (self.ENDPOINT, str(funder_id))
        return Works(context=context)


class Members(Endpoint):

    CURSOR_AS_ITER_METHOD = False

    ENDPOINT = 'members'

    FILTER_VALIDATOR = {
        'prefix': None,
        'has-public-references': validators.is_bool,
        'backfile-doi-count': validators.is_integer,
        'current-doi-count': validators.is_integer
    }

    def query(self, *args):
        """
        This method retrieve an iterable object that implements the method
        __iter__. The arguments given will compose the parameters in the
        request url.

        args: strings (String)

        return: iterable object of Members metadata

        Example:
            >>> from crossref.restful import Members
            >>> members = Members().query('Korean Association')
            members.query('Korean Association').url
            'https://api.crossref.org/journals?query=Public+Health+Health+Science'
            >>> next(iter(members.query('Korean Association')))
            {'prefix': [{'value': '10.20433', 'public-references': False,
            'name': 'The New Korean Philosophical Association'}], 'counts': {'total-dois': 0, 'backfile-dois': 0,
            'current-dois': 0}, 'coverage': {'references-backfile': 0, 'references-current': 0,
            'abstracts-current': 0, 'update-policies-backfile': 0, 'orcids-current': 0, 'orcids-backfile': 0,
            'licenses-current': 0, 'affiliations-backfile': 0, 'licenses-backfile': 0, 'update-policies-current': 0,
            'resource-links-current': 0, 'resource-links-backfile': 0, 'award-numbers-backfile': 0,
            'abstracts-backfile': 0, 'funders-current': 0, 'funders-backfile': 0, 'affiliations-current': 0,
            'award-numbers-current': 0}, 'flags': {'deposits-orcids-backfile': False,
            'deposits-references-backfile': False, 'deposits-licenses-current': False, 'deposits': False,
            'deposits-abstracts-current': False, 'deposits-award-numbers-current': False, 'deposits-articles': False,
            'deposits-resource-links-backfile': False, 'deposits-funders-current': False,
            'deposits-award-numbers-backfile': False, 'deposits-references-current': False,
            'deposits-abstracts-backfile': False, 'deposits-funders-backfile': False,
            'deposits-update-policies-current': False, 'deposits-orcids-current': False,
            'deposits-licenses-backfile': False, 'deposits-affiliations-backfile': False,
            'deposits-update-policies-backfile': False, 'deposits-resource-links-current': False,
            'deposits-affiliations-current': False}, 'names': ['The New Korean Philosophical Association'],
            'breakdowns': {'dois-by-issued-year': []}, 'location': 'Dongsin Tower, 4th Floor 5, Mullae-dong 6-ga,
            Mullae-dong 6-ga Seoul 150-096 South Korea', 'prefixes': ['10.20433'],
            'last-status-check-time': 1496034177684, 'id': 8334, 'tokens': ['the', 'new', 'korean', 'philosophical',
            'association'], 'primary-name': 'The New Korean Philosophical Association'}
        """
        context = str(self.context)
        request_url = build_url_endpoint(self.ENDPOINT)
        request_params = dict(self.request_params)

        if args:
            request_params['query'] = ' '.join([str(i) for i in args])

        return self.__class__(request_url=request_url, request_params=request_params, context=context, etiquette=self.etiquette, timeout=self.timeout)

    def filter(self, **kwargs):
        """
        This method retrieve an iterable object that implements the method
        __iter__. The arguments given will compose the parameters in the
        request url.

        This method can be used compounded and recursively with query, filter,
        order, sort and facet methods.

        kwargs: valid FILTER_VALIDATOR arguments.

        return: iterable object of Members metadata

        Example:
            >>> from crossref.restful import Members
            >>> members = Members()
            >>> query = members.filter(has_public_references='true')
            >>> for item in query:
            ...     print(item['prefix'])
            ...
            [{u'public-references': False, u'name': u'Open Library of Humanities', u'value': u'10.16995'}, {u'public-references': True, u'name': u'Martin Eve', u'value': u'10.7766'}]
            [{u'public-references': True, u'name': u'Institute of Business Research', u'value': u'10.24122'}]
            ...
        """
        context = str(self.context)
        request_url = build_url_endpoint(self.ENDPOINT, context)
        request_params = dict(self.request_params)

        for fltr, value in kwargs.items():
            decoded_fltr = fltr.replace('__', '.').replace('_', '-')
            if decoded_fltr not in self.FILTER_VALIDATOR.keys():
                raise UrlSyntaxError(
                    'Filter %s specified but there is no such filter for this route. Valid filters for this route are: %s' % (
                        str(decoded_fltr),
                        ', '.join(self.FILTER_VALIDATOR.keys())
                    )
                )

            if self.FILTER_VALIDATOR[decoded_fltr] is not None:
                self.FILTER_VALIDATOR[decoded_fltr](str(value))

            if 'filter' not in request_params:
                request_params['filter'] = decoded_fltr + ':' + str(value)
            else:
                request_params['filter'] += ',' + decoded_fltr + ':' + str(value)

        return self.__class__(request_url=request_url, request_params=request_params, context=context, etiquette=self.etiquette, timeout=self.timeout)

    def member(self, member_id, only_message=True):
        """
        This method retrive a crossref member metadata related to the
        given member_id.

        args: Member ID (Integer)

        Example:
            >>> from crossref.restful import Members
            >>> members = Members()
            >>> members.member(101)
            {'prefix': [{'value': '10.1024', 'public-references': False,
            'name': 'Hogrefe Publishing Group'}, {'value': '10.1027', 'public-references': False,
            'name': 'Hogrefe Publishing Group'}, {'value': '10.1026', 'public-references': False,
            'name': 'Hogrefe Publishing Group'}], 'counts': {'total-dois': 35039, 'backfile-dois': 31430,
            'current-dois': 3609}, 'coverage': {'references-backfile': 0.3601972758769989,
            'references-current': 0.019118869677186012, 'abstracts-current': 0.0,
            'update-policies-backfile': 0.0, 'orcids-current': 0.0, 'orcids-backfile': 0.0,
            'licenses-current': 0.0, 'affiliations-backfile': 0.05685650557279587,
            'licenses-backfile': 0.0, 'update-policies-current': 0.0, 'resource-links-current': 0.0,
            'resource-links-backfile': 0.0, 'award-numbers-backfile': 0.0, 'abstracts-backfile': 0.0,
            'funders-current': 0.0, 'funders-backfile': 0.0, 'affiliations-current': 0.15710723400115967,
            'award-numbers-current': 0.0}, 'flags': {'deposits-orcids-backfile': False,
            'deposits-references-backfile': True, 'deposits-licenses-current': False, 'deposits': True,
            'deposits-abstracts-current': False, 'deposits-award-numbers-current': False,
            'deposits-articles': True, 'deposits-resource-links-backfile': False,
            'deposits-funders-current': False, 'deposits-award-numbers-backfile': False,
            'deposits-references-current': True, 'deposits-abstracts-backfile': False,
            'deposits-funders-backfile': False, 'deposits-update-policies-current': False,
            'deposits-orcids-current': False, 'deposits-licenses-backfile': False,
            'deposits-affiliations-backfile': True, 'deposits-update-policies-backfile': False,
            'deposits-resource-links-current': False, 'deposits-affiliations-current': True},
            'names': ['Hogrefe Publishing Group'], 'breakdowns': {'dois-by-issued-year':
            [[2003, 2329], [2004, 2264], [2002, 2211], [2005, 2204], [2006, 2158], [2007, 2121], [2016, 1954],
            [2008, 1884], [2015, 1838], [2012, 1827], [2013, 1805], [2014, 1796], [2009, 1760], [2010, 1718],
            [2011, 1681], [2001, 1479], [2000, 1477], [1999, 1267], [2017, 767], [1997, 164], [1996, 140],
            [1998, 138], [1995, 103], [1994, 11], [1993, 11], [0, 1]]},
            'location': 'Langgass-Strasse 76 Berne CH-3000 Switzerland', 'prefixes': ['10.1024', '10.1027',
            '10.1026'], 'last-status-check-time': 1496034132646, 'id': 101, 'tokens': ['hogrefe', 'publishing',
            'group'], 'primary-name': 'Hogrefe Publishing Group'}
        """
        request_url = build_url_endpoint(
            '/'.join([self.ENDPOINT, str(member_id)])
        )
        request_params = {}

        result = self.do_http_request(
            'get',
            request_url,
            data=request_params,
            custom_header=self.custom_header,
            timeout=self.timeout
        )

        if result.status_code == 404:
            return

        result = result.json()

        return result['message'] if only_message is True else result

    def member_exists(self, member_id):
        """
        This method retrieve a boolean according to the existence of a crossref
        member. It returns False if the API results a 404 status code.

        args: Crossref allowed document Type (String)

        return: Boolean

        Example 1:
            >>> from crossref.restful import Members
            >>> members = Members()
            >>> members.member_exists(101)
            True

        Example 2:
            >>> from crossref.restful import Members
            >>> members = Members()
            >>> members.member_exists(88888)
            False
        """
        request_url = build_url_endpoint(
            '/'.join([self.ENDPOINT, str(member_id)])
        )
        request_params = {}

        result = self.do_http_request(
            'get',
            request_url,
            data=request_params,
            only_headers=True,
            custom_header=self.custom_header,
            timeout=self.timeout
        )

        if result.status_code == 404:
            return False

        return True

    def works(self, member_id):
        """
        This method retrieve a iterable of Works of the given member.

        args: Member ID (Integer)

        return: Works()
        """
        context = '%s/%s' % (self.ENDPOINT, str(member_id))
        return Works(context=context)


class Types(Endpoint):

    CURSOR_AS_ITER_METHOD = False

    ENDPOINT = 'types'

    def type(self, type_id, only_message=True):
        """
        This method retrive a crossref document type metadata related to the
        given type_id.

        args: Crossref allowed document Types (String)

        Example:
            >>> types.type('journal-article')
            {'label': 'Journal Article', 'id': 'journal-article'}
        """
        request_url = build_url_endpoint(
            '/'.join([self.ENDPOINT, str(type_id)])
        )
        request_params = {}

        result = self.do_http_request(
            'get',
            request_url,
            data=request_params,
            custom_header=self.custom_header,
            timeout=self.timeout
        )

        if result.status_code == 404:
            return

        result = result.json()

        return result['message'] if only_message is True else result

    def all(self):
        """
        This method retrieve an iterator with all the available types.

        return: iterator of crossref document types

        Example:
            >>> from crossref.restful import Types
            >>> types = Types()
            >>> [i for i in types.all()]
            [{'label': 'Book Section', 'id': 'book-section'},
            {'label': 'Monograph', 'id': 'monograph'},
            {'label': 'Report', 'id': 'report'},
            {'label': 'Book Track', 'id': 'book-track'},
            {'label': 'Journal Article', 'id': 'journal-article'},
            {'label': 'Part', 'id': 'book-part'},
            ...
            }]
        """
        request_url = build_url_endpoint(self.ENDPOINT, self.context)
        request_params = dict(self.request_params)

        result = self.do_http_request(
            'get',
            request_url,
            data=request_params,
            custom_header=self.custom_header,
            timeout=self.timeout
        )

        if result.status_code == 404:
            raise StopIteration()

        result = result.json()

        for item in result['message']['items']:
            yield item

    def type_exists(self, type_id):
        """
        This method retrieve a boolean according to the existence of a crossref
        document type. It returns False if the API results a 404 status code.

        args: Crossref allowed document Type (String)

        return: Boolean

        Example 1:
            >>> from crossref.restful import Types
            >>> types = Types()
            >>> types.type_exists('journal-article')
            True

        Example 2:
            >>> from crossref.restful import Types
            >>> types = Types()
            >>> types.type_exists('unavailable type')
            False
        """
        request_url = build_url_endpoint(
            '/'.join([self.ENDPOINT, str(type_id)])
        )
        request_params = {}

        result = self.do_http_request(
            'get',
            request_url,
            data=request_params,
            only_headers=True,
            custom_header=self.custom_header,
            timeout=self.timeout
        )

        if result.status_code == 404:
            return False

        return True

    def works(self, type_id):
        """
        This method retrieve a iterable of Works of the given type.

        args: Crossref allowed document Types (String)

        return: Works()
        """
        context = '%s/%s' % (self.ENDPOINT, str(type_id))
        return Works(context=context)


class Prefixes(Endpoint):

    CURSOR_AS_ITER_METHOD = False

    ENDPOINT = 'prefixes'

    def prefix(self, prefix_id, only_message=True):
        """
        This method retrieve a json with the given Prefix metadata

        args: Crossref Prefix (String)

        return: JSON

        Example:
            >>> from crossref.restful import Prefixes
            >>> prefixes = Prefixes()
            >>> prefixes.prefix('10.1590')
            {'name': 'FapUNIFESP (SciELO)', 'member': 'http://id.crossref.org/member/530',
            'prefix': 'http://id.crossref.org/prefix/10.1590'}
        """
        request_url = build_url_endpoint(
            '/'.join([self.ENDPOINT, str(prefix_id)])
        )
        request_params = {}

        result = self.do_http_request(
            'get',
            request_url,
            data=request_params,
            custom_header=self.custom_header,
            timeout=self.timeout
        )

        if result.status_code == 404:
            return

        result = result.json()

        return result['message'] if only_message is True else result

    def works(self, prefix_id):
        """
        This method retrieve a iterable of Works of the given prefix.

        args: Crossref Prefix (String)

        return: Works()
        """
        context = '%s/%s' % (self.ENDPOINT, str(prefix_id))
        return Works(context=context)


class Journals(Endpoint):

    CURSOR_AS_ITER_METHOD = False

    ENDPOINT = 'journals'

    def query(self, *args):
        """
        This method retrieve an iterable object that implements the method
        __iter__. The arguments given will compose the parameters in the
        request url.

        args: strings (String)

        return: iterable object of Journals metadata

        Example:
            >>> from crossref.restful import Journals
            >>> journals = Journals().query('Public Health', 'Health Science')
            >>> journals.url
            'https://api.crossref.org/journals?query=Public+Health+Health+Science'
            >>> next(iter(journals))
            {'last-status-check-time': None, 'counts': None, 'coverage': None,
            'publisher': 'ScopeMed International Medical Journal Managment and Indexing System',
            'flags': None, 'breakdowns': None, 'ISSN': ['2320-4664', '2277-338X'],
            'title': 'International Journal of Medical Science and Public Health'}
        """
        context = str(self.context)
        request_url = build_url_endpoint(self.ENDPOINT)
        request_params = dict(self.request_params)

        if args:
            request_params['query'] = ' '.join([str(i) for i in args])

        return self.__class__(request_url=request_url, request_params=request_params, context=context, etiquette=self.etiquette, timeout=self.timeout)

    def journal(self, issn, only_message=True):
        """
        This method retrieve a json with the given ISSN metadata

        args: Journal ISSN (String)

        return: Journal JSON data

        Example:
            >>> from crossref.restful import Journals
            >>> journals = Journals()
            >>> journals.journal('2277-338X')
            {'last-status-check-time': None, 'counts': None, 'coverage': None,
            'publisher': 'ScopeMed International Medical Journal Managment and Indexing System',
            'flags': None, 'breakdowns': None, 'ISSN': ['2320-4664', '2277-338X'],
            'title': 'International Journal of Medical Science and Public Health'}
        """
        request_url = build_url_endpoint(
            '/'.join([self.ENDPOINT, str(issn)])
        )
        request_params = {}

        result = self.do_http_request(
            'get',
            request_url,
            data=request_params,
            custom_header=self.custom_header,
            timeout=self.timeout
        )

        if result.status_code == 404:
            return

        result = result.json()

        return result['message'] if only_message is True else result

    def journal_exists(self, issn):
        """
        This method retrieve a boolean according to the existence of a journal
        in the Crossref database. It returns False if the API results a 404
        status code.

        args: Journal ISSN (String)

        return: Boolean

        Example 1:
            >>> from crossref.restful import Journals
            >>> journals = Journals()
            >>> journals.journal_exists('2277-338X')
            True

        Example 2:
            >>> from crossref.restful import Journals
            >>> journals = Journals()
            >>> journals.journal_exists('9999-AAAA')
            False
        """
        request_url = build_url_endpoint(
            '/'.join([self.ENDPOINT, str(issn)])
        )
        request_params = {}

        result = self.do_http_request(
            'get',
            request_url,
            data=request_params,
            only_headers=True,
            custom_header=self.custom_header,
            timeout=self.timeout
        )

        if result.status_code == 404:
            return False

        return True

    def works(self, issn):
        """
        This method retrieve a iterable of Works of the given journal.

        args: Journal ISSN (String)

        return: Works()
        """

        context = '%s/%s' % (self.ENDPOINT, str(issn))
        return Works(context=context)


class Depositor(object):

    def __init__(self, prefix, api_user, api_key, etiquette=None,
                 use_test_server=False):
        self.do_http_request = HTTPRequest(throttle=False).do_http_request
        self.etiquette = etiquette or Etiquette()
        self.custom_header = {'user-agent': str(self.etiquette)}
        self.prefix = prefix
        self.api_user = api_user
        self.api_key = api_key
        self.use_test_server = use_test_server

    def get_endpoint(self, verb):
        subdomain = 'test' if self.use_test_server else 'doi'
        return "https://{}.crossref.org/servlet/{}".format(subdomain, verb)

    def register_doi(self, submission_id, request_xml):
        """
        This method registry a new DOI number in Crossref or update some DOI
        metadata.

        submission_id: Will be used as the submission file name. The file name
        could be used in future requests to retrieve the submission status.

        request_xml: The XML with the document metadata. It must be under
        compliance with the Crossref Submission Schema.
        """

        endpoint = self.get_endpoint('deposit')

        files = {
            'mdFile': ('%s.xml' % submission_id, request_xml)
        }

        params = {
            'operation': 'doMDUpload',
            'login_id': self.api_user,
            'login_passwd': self.api_key
        }

        result = self.do_http_request(
            'post',
            endpoint,
            data=params,
            files=files,
            custom_header=self.custom_header,
            timeout=self.timeout
        )

        return result

    def request_doi_status_by_filename(self, file_name, data_type='result'):
        """
        This method retrieve the DOI requests status.

        file_name: Used as unique ID to identify a deposit.

        data_type: [contents, result]
            contents - retrieve the XML submited by the publisher
            result - retrieve a JSON with the status of the submission
        """

        endpoint = self.get_endpoint('submissionDownload')

        params = {
            'usr': self.api_user,
            'pwd': self.api_key,
            'file_name': file_name,
            'type': data_type
        }

        result = self.do_http_request(
            'get',
            endpoint,
            data=params,
            custom_header=self.custom_header,
            timeout=self.timeout
        )

        return result

    def request_doi_status_by_batch_id(self, doi_batch_id, data_type='result'):
        """
        This method retrieve the DOI requests status.

        file_name: Used as unique ID to identify a deposit.

        data_type: [contents, result]
            contents - retrieve the XML submited by the publisher
            result - retrieve a XML with the status of the submission
        """

        endpoint = self.get_endpoint('submissionDownload')

        params = {
            'usr': self.api_user,
            'pwd': self.api_key,
            'doi_batch_id': doi_batch_id,
            'type': data_type
        }

        result = self.do_http_request(
            'get',
            endpoint,
            data=params,
            custom_header=self.custom_header,
            timeout=self.timeout
        )

        return result
